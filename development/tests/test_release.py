#!/usr/bin/env python3
"""Exercise Make targets in disposable Git repositories, with no GitHub access."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
GIT = shutil.which("git")
MAKE = shutil.which("make")
VERSION = re.search(r"^VERSION=(\S+)$", (ROOT / "jrnl.sh").read_text(), re.M).group(1)
TAG = f"v{VERSION}"
URL = "https://github.com/example/jrnl.git"


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="jrnl release tests ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.repo = self.base / "checkout with spaces"
        self.repo.mkdir()
        self.bin = self.base / "bin"
        self.bin.mkdir()
        self.remote = self.base / "remote.git"
        self.log = self.base / "calls.jsonl"
        self.home = self.base / "home"
        self.home.mkdir()
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith(("GIT_", "GH_", "GITHUB_"))
                    and k not in ("BASH_ENV", "ENV", "MAKEFLAGS", "MFLAGS", "MAKEFILES")}
        self.env.update(HOME=str(self.home), PATH=f"{self.bin}:/usr/bin:/bin",
                        GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                        GIT_AUTHOR_NAME="Test", GIT_AUTHOR_EMAIL="test@example.invalid",
                        GIT_COMMITTER_NAME="Test", GIT_COMMITTER_EMAIL="test@example.invalid",
                        TEST_LOG=str(self.log), TEST_GIT=GIT, TEST_REMOTE=str(self.remote))
        for name in ("Makefile", "jrnl.sh", "jrnl.zsh", "install.sh",
                     "development/release.sh", "vendor/clack-bash/select.sh"):
            target = self.repo / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, target)
        self.git("init", "-q")
        self.git("init", "-q", "--bare", str(self.remote))
        self.git("remote", "add", "origin", URL)
        self.snapshot()
        # Only transport is redirected; real Git creates/verifies tags and pushes
        # to the disposable bare repo. All GitHub CLI calls are replaced locally.
        self.mock("git", '''
args = sys.argv[1:]
if args[0] in ("push", "ls-remote"):
    log("git", args)
    if os.environ.get("TEST_GIT_FAIL") == args[0]:
        sys.exit(1)
    args = [os.environ["TEST_REMOTE"] if x.startswith(("https://", "git@", "ssh://")) else x for x in args]
os.execv(os.environ["TEST_GIT"], [os.environ["TEST_GIT"], *args])
''')
        self.mock("gh", '''
args = sys.argv[1:]
log("gh", args)
mode = os.environ.get("TEST_GH_MODE", "")
if args[:2] == ["auth", "status"]:
    sys.exit(1 if mode == "auth-fail" else 0)
if args[0] == "api":
    if any("/releases?" in x for x in args):
        if mode == "api-fail":
            sys.exit(1)
        print(os.environ.get("TEST_EXISTING", ""))
    else:
        print("false" if mode == "read-only" else "true")
    sys.exit(0)
if args[:2] == ["release", "create"]:
    sys.exit(1 if mode == "create-fail" else 0)
sys.exit("Unexpected gh invocation")
''')

    def mock(self, name, body):
        path = self.bin / name
        path.write_text(f"#!{sys.executable}\n" + '''import json, os, sys

def log(tool, args):
    with open(os.environ["TEST_LOG"], "a") as stream:
        stream.write(json.dumps([tool, *args]) + "\\n")
''' + body)
        path.chmod(0o755)

    def git(self, *args, input=None):
        result = subprocess.run([GIT, *args], cwd=self.repo, env=self.env,
                                input=input, text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def snapshot(self, parent=None):
        # Plumbing creates fixture history without staging/committing user files.
        for path in self.repo.rglob("*"):
            if not path.is_file() or ".git" in path.relative_to(self.repo).parts:
                continue
            blob = self.git("hash-object", "-w", str(path))
            mode = "100755" if path.stat().st_mode & 0o111 else "100644"
            self.git("update-index", "--add", "--cacheinfo", mode, blob,
                     str(path.relative_to(self.repo)))
        tree = self.git("write-tree")
        parents = ["-p", parent] if parent else []
        commit = self.git("commit-tree", tree, *parents, input="Fixture\n")
        self.git("update-ref", "HEAD", commit)
        return commit

    def make(self, target, ok=True):
        result = subprocess.run([MAKE, target], cwd=self.repo, env=self.env,
                                text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def assert_no_publish(self):
        self.assertFalse(any(c[:2] == ["git", "push"] or c[:3] == ["gh", "release", "create"]
                             for c in self.calls()), self.calls())

    def test_install_delegates_and_installs(self):
        self.make("install")
        installed = self.home / ".local/bin/jrnl"
        self.assertTrue(os.access(installed, os.X_OK))
        self.assertEqual(installed.read_bytes(), (self.repo / "jrnl.sh").read_bytes())
        self.assertTrue((self.home / ".local/share/jrnl/jrnl.zsh").is_file())
        self.assertTrue((self.home / ".local/share/jrnl/clack-select.sh").is_file())
        self.make("install")

    def test_tag_is_annotated_at_head_and_never_pushes(self):
        self.make("tag")
        self.assertEqual(self.git("cat-file", "-t", f"refs/tags/{TAG}"), "tag")
        self.assertEqual(self.git("rev-parse", f"{TAG}^{{commit}}"), self.git("rev-parse", "HEAD"))
        before = self.git("rev-parse", TAG)
        self.assertIn("already exists", self.make("tag", ok=False))
        self.assertEqual(self.git("rev-parse", TAG), before)
        self.assertEqual(self.calls(), [])

    def test_version_is_read_from_project(self):
        script = self.repo / "jrnl.sh"
        script.write_text(script.read_text().replace(f"VERSION={VERSION}", "VERSION=7.8.9b"))
        self.snapshot(parent=self.git("rev-parse", "HEAD"))
        self.make("tag")
        self.assertEqual(self.git("cat-file", "-t", "refs/tags/v7.8.9b"), "tag")

    def test_dirty_staged_and_untracked_trees_fail(self):
        path = self.repo / "jrnl.sh"
        path.write_text(path.read_text() + "\n# change\n")
        self.assertIn("clean", self.make("tag", ok=False))
        blob = self.git("hash-object", "-w", str(path))
        self.git("update-index", "--cacheinfo", "100755", blob, "jrnl.sh")
        self.assertIn("clean", self.make("tag", ok=False))
        self.git("read-tree", "HEAD")
        shutil.copy2(ROOT / "jrnl.sh", path)
        (self.repo / "untracked").touch()
        self.assertIn("clean", self.make("tag", ok=False))
        self.assert_no_publish()

    def test_unfinished_operation_fails(self):
        (self.repo / ".git/MERGE_HEAD").write_text(self.git("rev-parse", "HEAD") + "\n")
        self.assertIn("in-progress", self.make("tag", ok=False))

    def test_release_requires_annotated_tag_at_head(self):
        self.assertIn("make tag", self.make("release", ok=False))
        self.git("update-ref", f"refs/tags/{TAG}", self.git("rev-parse", "HEAD"))
        self.assertIn("Annotated tag", self.make("release", ok=False))
        self.git("update-ref", "-d", f"refs/tags/{TAG}")
        self.make("tag")
        (self.repo / "new-file").touch()
        self.snapshot(parent=self.git("rev-parse", "HEAD"))
        self.assertIn("does not point to HEAD", self.make("release", ok=False))
        self.assert_no_publish()

    def test_release_pushes_only_version_tag_and_generates_notes(self):
        self.make("tag")
        tag_data = self.git("cat-file", "tag", TAG).replace(f"tag {TAG}\n", "tag unrelated\n")
        extra = self.git("hash-object", "-t", "tag", "-w", "--stdin", input=tag_data + "\n")
        self.git("update-ref", "refs/tags/unrelated", extra)
        self.git("config", "push.followTags", "true")
        self.env["GH_REPO"] = "wrong/repo"
        self.make("release")
        self.assertEqual(self.git("--git-dir", str(self.remote), "for-each-ref", "--format=%(refname)"),
                         f"refs/tags/{TAG}")
        create = next(c for c in self.calls() if c[:3] == ["gh", "release", "create"])
        self.assertIn("--generate-notes", create)
        self.assertIn("--verify-tag", create)
        self.assertIn(f"jrnl {TAG}", create)
        self.assertEqual(create[create.index("--repo") + 1], "github.com/example/jrnl")
        # A matching remote tag is safe to reuse after a publication failure.
        self.make("release")

    def test_existing_release_fails_before_push(self):
        self.make("tag")
        self.env["TEST_EXISTING"] = TAG
        self.assertIn("already exists", self.make("release", ok=False))
        self.assertTrue(any("--paginate" in c for c in self.calls()))
        self.assert_no_publish()

    def test_auth_api_and_permission_failures_do_not_push(self):
        self.make("tag")
        for mode in ("auth-fail", "api-fail", "read-only"):
            with self.subTest(mode=mode):
                self.env["TEST_GH_MODE"] = mode
                self.make("release", ok=False)
                self.assert_no_publish()

    def test_missing_gh_fails(self):
        (self.bin / "gh").unlink()
        self.assertIn("gh is required", self.make("release", ok=False))
        self.assert_no_publish()

    def test_missing_or_ambiguous_origin_fails(self):
        self.make("tag")
        self.git("remote", "remove", "origin")
        self.assertIn("origin push URL", self.make("release", ok=False))
        self.git("remote", "add", "origin", URL)
        self.git("config", "--add", "remote.origin.pushurl", URL)
        self.git("config", "--add", "remote.origin.pushurl", "git@github.com:other/repo.git")
        self.assertIn("exactly one", self.make("release", ok=False))
        self.assert_no_publish()

    def test_ssh_push_destination_is_used_for_gh(self):
        self.make("tag")
        self.git("config", "remote.origin.pushurl", "git@github.com:publisher/jrnl.git")
        self.make("release")
        create = next(c for c in self.calls() if c[:3] == ["gh", "release", "create"])
        self.assertIn("github.com/publisher/jrnl", create)

    def test_conflicting_remote_tag_fails(self):
        self.make("tag")
        # Use the same commit but a different annotation: never replace that tag.
        tag_data = self.git("cat-file", "tag", TAG) + "\nDifferent annotation\n"
        obj = self.git("hash-object", "-t", "tag", "-w", "--stdin", input=tag_data)
        self.git("--git-dir", str(self.remote), "fetch", "-q", str(self.repo), "HEAD")
        self.git("--git-dir", str(self.remote), "hash-object", "-t", "tag", "-w", "--stdin", input=tag_data)
        self.git("--git-dir", str(self.remote), "update-ref", f"refs/tags/{TAG}", obj)
        self.assertIn("differs", self.make("release", ok=False))
        self.assert_no_publish()

    def test_remote_read_failure_does_not_push(self):
        self.make("tag")
        self.env["TEST_GIT_FAIL"] = "ls-remote"
        self.assertIn("Cannot check remote tags", self.make("release", ok=False))
        self.assert_no_publish()

    def test_push_failure_does_not_create_release(self):
        self.make("tag")
        self.env["TEST_GIT_FAIL"] = "push"
        self.assertIn("Tag push failed", self.make("release", ok=False))
        self.assertFalse(any(c[:3] == ["gh", "release", "create"] for c in self.calls()))

    def test_create_failure_preserves_tag(self):
        self.make("tag")
        self.env["TEST_GH_MODE"] = "create-fail"
        self.assertIn("remains on origin", self.make("release", ok=False))
        self.assertEqual(self.git("--git-dir", str(self.remote), "rev-parse", f"{TAG}^{{commit}}"),
                         self.git("rev-parse", "HEAD"))


if __name__ == "__main__":
    unittest.main()
