#!/usr/bin/env python3
"""Integration tests using temporary homes; never changes your shell config."""
import errno
import fcntl
import os
from pathlib import Path
import pty
import re
import select
import shlex
import shutil
import signal
import struct
import subprocess
import termios
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "jrnl.sh"


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="jrnl-test-")
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name).resolve()
        self.script = SCRIPT
        self.installed = self.home / ".local/bin/jrnl"
        self.integration = self.home / ".local/share/jrnl/jrnl.zsh"
        self.log = self.home / "notes with spaces" / "engineering.md"
        self.bin = self.home / "bin"
        self.bin.mkdir()
        self.env = os.environ.copy()
        for key in ("ZDOTDIR", "BASH_ENV", "ENV", "JRNL_FILE", "NO_COLOR"):
            self.env.pop(key, None)
        self.env.update(HOME=str(self.home), PATH=f"{self.bin}:{os.environ['PATH']}",
                        JRNL_FILE=str(self.log), JRNL_TEST_NOW="2026-09-26 13:26:21")
        self.mock("date", 'printf "%s\\n" "$JRNL_TEST_NOW"\n')

    def mock(self, name, body):
        path = self.bin / name
        path.write_text("#!/bin/sh\n" + body)
        path.chmod(0o755)

    def run_jrnl(self, *args, input=None, ok=True):
        result = subprocess.run([str(self.script), *args], env=self.env,
                                input=input, text=True, capture_output=True, timeout=10)
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def install(self, *args, root=ROOT, ok=True):
        result = subprocess.run([str(root / "install.sh"), *args], env=self.env,
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        return result

    def zsh(self, code):
        result = subprocess.run(["zsh", "-dfc", code], env=self.env, cwd=self.home,
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def wait_for(self, predicate):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.01)
        self.fail("Timed out waiting for writer synchronization")

    def test_help_version_and_invalid_input(self):
        for flag in ("-h", "--help"):
            help_text = self.run_jrnl(flag).stdout
            self.assertIn("Usage:", help_text)
            self.assertIn("--show", help_text)
            self.assertNotIn("--cat", help_text)
        for flag in ("-V", "--version"):
            self.assertEqual(self.run_jrnl(flag).stdout, "jrnl 0.1.2a\n")
        self.assertIn("Usage:", self.run_jrnl().stdout)
        self.run_jrnl("--typo", ok=False)
        self.assertIn("Unknown option: --cat", self.run_jrnl("--cat", ok=False).stderr)
        self.run_jrnl("--show", "unexpected", ok=False)
        self.run_jrnl("--", ok=False)
        self.run_jrnl("   ", ok=False)
        self.run_jrnl("two\nlines", ok=False)
        self.run_jrnl("two\rlines", ok=False)
        self.assertFalse(self.log.exists())

    def test_newest_entries_and_days_first(self):
        first = self.run_jrnl("Investigated", "strange network traffic today.")
        self.assertIn(self.log.name, first.stdout)
        self.assertIn(str(self.log.parent) + "/", first.stdout)
        self.assertIn("[13:26:21] Investigated strange network traffic today.", first.stdout)
        self.assertEqual(self.log.read_text(),
                         "## 2026-09-26\n\n###### [13:26:21]\n\n"
                         "Investigated strange network traffic today.\n\n")
        self.env["JRNL_TEST_NOW"] = "2026-09-26 14:00:00"
        self.run_jrnl("Second entry")
        self.assertEqual(self.log.read_text(),
                         "## 2026-09-26\n\n###### [14:00:00]\n\nSecond entry\n\n"
                         "###### [13:26:21]\n\nInvestigated strange network traffic today.\n\n")
        self.env["JRNL_TEST_NOW"] = "2026-09-27 09:00:00"
        self.run_jrnl("Next day")
        self.assertEqual(self.log.read_text(),
                         "## 2026-09-27\n\n###### [09:00:00]\n\nNext day\n\n"
                         "## 2026-09-26\n\n###### [14:00:00]\n\nSecond entry\n\n"
                         "###### [13:26:21]\n\nInvestigated strange network traffic today.\n\n")
        self.env["JRNL_TEST_NOW"] = "2026-09-26 15:00:00"
        self.run_jrnl("Back to an existing date")
        self.assertEqual(self.log.read_text().count("## 2026-09-26"), 1)
        self.assertIn("## 2026-09-26\n\n###### [15:00:00]\n\nBack", self.log.read_text())

    def test_literal_text_show_and_check(self):
        entry = r"Why? <>{}#[] ., %s \\n $HOME $(echo nope) `whoami` & | ; ! café"
        self.run_jrnl(entry)
        self.run_jrnl("--", "--help")
        contents = self.log.read_text()
        self.assertIn(entry, contents)
        self.assertIn("###### [13:26:21]\n\n--help", contents)
        self.assertEqual(self.run_jrnl("--show").stdout, contents)
        self.assertIn(str(self.log), self.run_jrnl("--check").stdout)

    def test_task_entry_and_literal_whitespace(self):
        task = "- [ ] ah now I get it! A `-` at sentence beginning needs a `--` to work and then the desired `-`."
        self.run_jrnl("--", task)
        self.assertEqual(self.log.read_text(),
                         "## 2026-09-26\n\n###### [13:26:21]\n\n" + task + "\n\n")
        literal = r"  Keep  $foo | \n 'quotes' and \backslashes\  "
        self.run_jrnl(literal)
        self.assertEqual(self.log.read_text(),
                         "## 2026-09-26\n\n###### [13:26:21]\n\n" + literal + "\n\n"
                         "###### [13:26:21]\n\n" + task + "\n\n")

    def test_old_entries_and_empty_date_sections(self):
        self.log.parent.mkdir()
        old = "[08:00:00] Existing  $text \\n remains.\n\n## 2026-09-25\n\nOlder text.\n\n"
        self.log.write_text("## 2026-09-26\n\n" + old)
        self.run_jrnl("New entry")
        self.assertEqual(self.log.read_text(),
                         "## 2026-09-26\n\n###### [13:26:21]\n\nNew entry\n\n" + old)
        self.log.write_text("## 2026-09-26\n\n\n## 2026-09-25\n\nOlder text.\n\n")
        self.run_jrnl("Fill empty day")
        self.assertEqual(self.log.read_text(),
                         "## 2026-09-26\n\n###### [13:26:21]\n\nFill empty day\n\n"
                         "## 2026-09-25\n\nOlder text.\n\n")

    def test_show_missing_journal_and_removed_cat(self):
        self.assertIn("Journal does not exist", self.run_jrnl("--show", ok=False).stderr)
        self.assertFalse(self.log.exists())
        self.run_jrnl("Keep me")
        before = self.log.read_bytes()
        self.run_jrnl("--cat", ok=False)
        self.assertEqual(self.log.read_bytes(), before)
        self.assertEqual(self.run_jrnl("--show").stdout, before.decode())

    def success_output(self, entry, styled=False):
        if styled:
            first = f"[\033[32m✓\033[0m] [\033[35m13:26:21\033[0m] \033[34m{entry}\033[0m\n"
            hint = "\033[33m[i] Show all entries with jrnl --show or open with jrnl -o\033[0m\n"
        else:
            first = f"[✓] [13:26:21] {entry}\n"
            hint = "[i] Show all entries with jrnl --show or open with jrnl -o\n"
        return (first + f"    was written to {self.log.name}\n"
                f"    in {self.log.parent}/\n\n" + hint)

    def test_success_output_and_noninteractive_color(self):
        self.env["TERM"] = "xterm-256color"
        entry = r"A literal %s, \n, $foo | and 'quotes'."
        result = self.run_jrnl(entry)
        self.assertEqual(result.stdout, self.success_output(entry))
        self.assertEqual(result.stderr, "")
        self.assertNotIn("\033", result.stdout)
        # A relative path and a symlink still report the actual destination.
        link = self.home / "alias.md"
        link.symlink_to(self.log)
        self.env["JRNL_FILE"] = os.path.relpath(link)
        self.assertEqual(self.run_jrnl(entry).stdout, self.success_output(entry))

    def run_jrnl_tty(self, entry):
        fd, slave = pty.openpty()
        process = subprocess.Popen([str(self.script), entry], env=self.env,
                                   stdin=subprocess.DEVNULL, stdout=slave, stderr=slave)
        os.close(slave)
        output = b""
        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if not select.select([fd], [], [], 0.1)[0]:
                    continue
                try:
                    chunk = os.read(fd, 65536)
                except OSError as error:
                    if error.errno != errno.EIO:
                        raise
                    break
                if not chunk:
                    break
                output += chunk
            self.assertEqual(process.wait(timeout=2), 0, output)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=2)
            os.close(fd)
        return output.decode().replace("\r\n", "\n")

    def test_terminal_color_boundaries_and_resets(self):
        for term in ("xterm-256color", "xterm", "ansi"):
            with self.subTest(term=term):
                self.env["TERM"] = term
                entry = "This is a test."
                self.assertEqual(self.run_jrnl_tty(entry), self.success_output(entry, styled=True))

    def test_terminal_no_color_and_dumb_fallback(self):
        for term, no_color in (("xterm-256color", "1"), ("xterm", "yes"), ("dumb", ""), (None, "")):
            with self.subTest(term=term, no_color=no_color):
                if term is None:
                    self.env.pop("TERM", None)
                else:
                    self.env["TERM"] = term
                self.env["NO_COLOR"] = no_color
                entry = "Plain text."
                output = self.run_jrnl_tty(entry)
                self.assertEqual(output, self.success_output(entry))
                self.assertNotIn("\033", output)

    def test_setup_preserves_config_and_is_repeatable(self):
        rc = self.home / ".zshrc"
        original = "# Keep this\nexport EXISTING=value\n"
        rc.write_text(original)
        path = self.home / "O'Brien $notes [work]" / "diary"
        self.run_jrnl("--setup", input=str(path) + "\n")
        configured = Path(str(path) + ".md")
        self.assertTrue(configured.is_file())
        self.assertEqual((self.home / ".zshrc.jrnl.bak").read_text(), original)
        self.assertTrue(rc.read_text().startswith(original))
        first_config = rc.read_bytes()
        first_stat = rc.stat()
        self.run_jrnl("--setup", input=str(path) + "\n")
        self.assertEqual(rc.read_bytes(), first_config)
        self.assertEqual(rc.stat().st_mtime_ns, first_stat.st_mtime_ns)
        self.assertEqual((self.home / ".zshrc.jrnl.bak").read_text(), original)
        self.assertEqual(rc.read_text().count("# >>> jrnl >>>"), 1)
        self.assertEqual(rc.read_text().count("export JRNL_FILE="), 1)
        self.assertNotIn(str(ROOT), rc.read_text())
        self.assertTrue(self.installed.is_file())
        self.assertTrue(self.integration.is_file())
        if shutil.which("zsh"):
            result = subprocess.run(["zsh", "-dfc", 'source "$HOME/.zshrc"; jrnl --check'],
                                    env=self.env, text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(str(configured), result.stdout)

    def test_setup_migrates_old_block_in_place(self):
        rc = self.home / ".zshrc"
        before = "# before\nexport BEFORE=1\n\n"
        after = "\n# after\nexport AFTER=2\n"
        original = before + "# >>> jrnl >>>\nsource /old/repo/jrnl.zsh\n# <<< jrnl <<<\n" + after
        rc.write_text(original)
        rc.chmod(0o640)
        self.run_jrnl("--setup", input="\n")
        self.assertTrue(rc.read_text().startswith(before))
        self.assertTrue(rc.read_text().endswith(after))
        self.assertNotIn("/old/repo", rc.read_text())
        self.assertEqual(rc.stat().st_mode & 0o777, 0o640)
        self.assertEqual((self.home / ".zshrc.jrnl.bak").read_text(), original)

    def test_installer_dry_run_and_reinstall(self):
        original = {p.relative_to(self.home): p.read_bytes() for p in self.home.rglob("*") if p.is_file()}
        self.assertIn("No changes made", self.install("--dry-run").stdout)
        self.assertFalse((self.home / ".local").exists())
        self.assertEqual(original, {p.relative_to(self.home): p.read_bytes() for p in self.home.rglob("*") if p.is_file()})
        self.assertIn("Usage:", self.install("--help").stdout)
        self.install("--dry-run", "extra", ok=False)
        self.install("--typo", ok=False)
        result = self.install()
        self.assertIn("jrnl 0.1.2a", result.stdout)
        self.assertIn("not on PATH", result.stdout)
        self.assertIn(str(self.installed), result.stdout)
        self.assertFalse((self.home / ".zshrc").exists())
        self.assertFalse(self.log.exists())
        self.assertEqual(self.installed.read_bytes(), SCRIPT.read_bytes())
        self.assertEqual(self.integration.read_bytes(), (ROOT / "jrnl.zsh").read_bytes())
        self.assertEqual(self.installed.stat().st_mode & 0o777, 0o755)
        self.assertEqual(self.integration.stat().st_mode & 0o777, 0o644)
        # An older installed copy is safely replaced; dry-run does not replace it.
        self.installed.write_text(self.installed.read_text().replace("VERSION=0.1.2a", "VERSION=0.0.1a"))
        old = self.installed.read_bytes()
        self.install("--dry-run")
        self.assertEqual(self.installed.read_bytes(), old)
        self.install()
        self.assertEqual(self.installed.read_bytes(), SCRIPT.read_bytes())

    def test_installed_files_survive_repo_move_and_removal(self):
        repo = self.home / "checkout with 'quotes' $ []"
        repo.mkdir()
        for name in ("jrnl.sh", "jrnl.zsh", "install.sh"):
            shutil.copy2(ROOT / name, repo / name)
        self.install(root=repo)
        self.script = self.installed
        self.run_jrnl("--setup", input="\n")
        moved = repo.with_name("moved checkout")
        repo.rename(moved)
        self.run_jrnl("Works after move")
        shutil.rmtree(moved)
        self.run_jrnl("Works after removal")
        self.run_jrnl("--setup", input="\n")
        for flag in ("-h", "--help", "-V", "--version", "--check", "--show"):
            self.run_jrnl(flag)
        self.run_jrnl("--", "--help")
        self.mock("open", 'printf "opened: %s\\n" "$1"\n')
        for flag in ("-o", "--open"):
            self.assertIn(str(self.log), self.run_jrnl(flag).stdout)
        result = self.zsh('source "$HOME/.zshrc"; source "$HOME/.zshrc"; jrnl "Via zsh"; command jrnl --version; print -r -- "$PATH"')
        self.assertIn("jrnl 0.1.2a", result.stdout)
        self.assertEqual(result.stdout.splitlines()[-1].split(":").count(str(self.installed.parent)), 1)
        self.assertIn("Via zsh", self.log.read_text())
        self.assertNotIn(str(repo), (self.home / ".zshrc").read_text())

    def test_installer_refuses_unrelated_destinations(self):
        self.installed.parent.mkdir(parents=True)
        self.installed.write_text("#!/bin/sh\n# another command\n")
        self.assertIn("Refusing to replace", self.install(ok=False).stderr)
        self.assertFalse(self.integration.exists())
        self.assertIn("another command", self.installed.read_text())
        self.installed.unlink()
        victim = self.home / "keep"
        victim.write_text("keep")
        self.installed.symlink_to(victim)
        self.install(ok=False)
        self.assertEqual(victim.read_text(), "keep")
        self.assertTrue(self.installed.is_symlink())

    def test_zsh_preserves_existing_aliases_and_functions(self):
        self.install()
        for definition, check in (("alias jrnl='print unrelated'", "alias jrnl"),
                                  ("jrnl() { print unrelated; }", "jrnl")):
            with self.subTest(definition=definition):
                result = self.zsh(definition + '; source "$HOME/.local/share/jrnl/jrnl.zsh"; ' + check)
                self.assertIn("unrelated", result.stdout)
                self.assertIn("was kept", result.stderr)

    def test_reloading_replaces_legacy_repo_wrapper(self):
        self.run_jrnl("--setup", input="\n")
        result = self.zsh('''source "$HOME/.zshrc"
# Recreate the prior wrapper: same body, but it invoked bash on a repo script.
functions[jrnl]=${functions[jrnl]/command /command bash }
unset _JRNL_WRAPPER
JRNL_SCRIPT=/removed-checkout/jrnl.sh
source "$HOME/.zshrc"
jrnl --version
''')
        self.assertEqual(result.stdout, "jrnl 0.1.2a\n")
        self.assertEqual(result.stderr, "")

    def test_setup_with_shell_sensitive_home_and_journal_paths(self):
        special_home = self.home / "home 'quoted' $notes [work]"
        special_home.mkdir()
        self.env["HOME"] = str(special_home)
        journal = special_home / "$(touch PWNED) `touch PWNED2` \\ !.md"
        self.run_jrnl("--setup", input=str(journal) + "\n")
        result = self.zsh('source "$HOME/.zshrc"; jrnl --check; jrnl "Safe path"')
        self.assertIn(str(journal), result.stdout)
        self.assertIn("Safe path", journal.read_text())
        self.assertFalse((self.home / "PWNED").exists())
        self.assertFalse((self.home / "PWNED2").exists())

    def test_failed_setup_preserves_backup_and_unrelated_configuration(self):
        rc = self.home / ".zshrc"
        backup = self.home / ".zshrc.jrnl.bak"
        backup.write_text("previous backup")
        for original in ("# <<< jrnl <<<\n# unrelated\n",
                         "# >>> jrnl >>>\n# >>> jrnl >>>\n# <<< jrnl <<<\n"):
            with self.subTest(original=original):
                rc.write_text(original)
                self.run_jrnl("--setup", input="\n", ok=False)
                self.assertEqual(rc.read_text(), original)
                self.assertEqual(backup.read_text(), "previous backup")
        rc.write_text("# original\n")
        backup.unlink()
        victim = self.home / "keep-backup-target"
        victim.write_text("keep")
        backup.symlink_to(victim)
        self.run_jrnl("--setup", input="\n", ok=False)
        self.assertEqual(rc.read_text(), "# original\n")
        self.assertEqual(victim.read_text(), "keep")

    def test_missing_config_prompts_and_keeps_first_entry(self):
        self.env.pop("JRNL_FILE")
        result = self.run_jrnl("First entry", input="~/new folder/diary.md\n")
        self.assertIn("No journal path", result.stderr)
        self.assertIn("First entry", (self.home / "new folder/diary.md").read_text())
        self.assertIn("export JRNL_FILE=", (self.home / ".zshrc").read_text())

    def test_cancel_and_malformed_config_leave_files_intact(self):
        self.env.pop("JRNL_FILE")
        self.run_jrnl("Entry", input="", ok=False)
        self.assertFalse((self.home / ".zshrc").exists())
        rc = self.home / ".zshrc"
        original = "# >>> jrnl >>>\nkeep all this\n"
        rc.write_text(original)
        self.run_jrnl("--setup", input=str(self.log) + "\n", ok=False)
        self.assertEqual(rc.read_text(), original)
        self.assertFalse(Path(str(rc) + ".lock").exists())

    def test_zdotdir_and_symlinked_configuration(self):
        config_dir = self.home / "zsh config"
        config_dir.mkdir()
        self.env["ZDOTDIR"] = str(config_dir)
        target = self.home / "actual-zshrc"
        target.write_text("# dotfiles\n")
        (config_dir / ".zshrc").symlink_to(target)
        self.run_jrnl("--setup", input=str(self.log) + "\n")
        self.assertTrue((config_dir / ".zshrc").is_symlink())
        self.assertIn("export JRNL_FILE=", target.read_text())
        self.assertFalse((self.home / ".zshrc").exists())

    def test_symlink_permissions_and_busy_lock(self):
        target = self.home / "real.md"
        target.write_text("## 2026-09-25\n\n[08:00:00] Keep me\n")
        target.chmod(0o640)
        self.log.parent.mkdir()
        self.log.symlink_to(target)
        self.run_jrnl("New entry")
        self.assertTrue(self.log.is_symlink())
        self.assertIn("Keep me", target.read_text())
        self.assertEqual(target.stat().st_mode & 0o777, 0o640)
        before = target.read_bytes()
        lock = Path(str(target) + ".lock")
        lock.mkdir()
        self.run_jrnl("Busy entry", ok=False)
        self.assertEqual(target.read_bytes(), before)
        self.assertTrue(lock.is_dir())

    def test_live_lock_is_not_stolen(self):
        self.run_jrnl("Keep me")
        before = self.log.read_bytes()
        owner = Path(str(self.log) + ".lock") / str(os.getpid())
        owner.mkdir(parents=True)
        self.assertIn("File is busy", self.run_jrnl("Blocked", ok=False).stderr)
        self.assertTrue(owner.is_dir())
        self.assertEqual(self.log.read_bytes(), before)

    def test_failed_rewrite_is_atomic_and_releases_lock(self):
        self.run_jrnl("Keep me")
        before = self.log.read_bytes()
        self.mock("awk", "printf 'incomplete rewrite\\n'\nexit 42\n")
        self.run_jrnl("Failed", ok=False)
        self.assertEqual(self.log.read_bytes(), before)
        self.assertFalse(Path(str(self.log) + ".lock").exists())
        self.assertEqual(list(self.log.parent.glob("*.tmp.*")), [])

    def test_killed_writer_leaves_original_and_recovers_stale_lock(self):
        self.run_jrnl("Keep me")
        before = self.log.read_bytes()
        self.mock("awk", 'printf "incomplete rewrite\\n"\n: > "$HOME/writer-ready"\nwhile :; do sleep 1; done\n')
        writer = subprocess.Popen([str(SCRIPT), "Killed entry"], env=self.env,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                  start_new_session=True)
        def stop():
            if writer.poll() is None:
                os.killpg(writer.pid, signal.SIGKILL)
            writer.wait(timeout=5)
        self.addCleanup(stop)
        self.wait_for(lambda: (self.home / "writer-ready").exists())
        lock = Path(str(self.log) + ".lock")
        self.assertTrue((lock / str(writer.pid)).is_dir())
        stop()
        self.assertEqual(self.log.read_bytes(), before)
        (self.bin / "awk").unlink()
        self.run_jrnl("Recovered entry")
        self.assertIn("Keep me", self.log.read_text())
        self.assertIn("Recovered entry", self.log.read_text())
        self.assertNotIn("Killed entry", self.log.read_text())
        self.assertFalse(lock.exists())

    def test_competing_stale_lock_recovery_keeps_new_owner_safe(self):
        self.run_jrnl("Keep me")
        before = self.log.read_bytes()
        departed = subprocess.Popen(["true"])
        departed.wait(timeout=5)
        lock = Path(str(self.log) + ".lock")
        dead_owner = lock / str(departed.pid)
        dead_owner.mkdir(parents=True)
        self.env["JRNL_DEAD_OWNER"] = str(dead_owner.resolve())
        real_rmdir = shlex.quote(shutil.which("rmdir"))
        self.mock("rmdir", '''if [ "$2" = "$JRNL_DEAD_OWNER" ]; then
    : > "$HOME/ready-$JRNL_RACER"
    while [ ! -e "$HOME/claim-$JRNL_RACER" ]; do sleep 0.02; done
fi
exec ''' + real_rmdir + ' "$@"\n')
        self.mock("date", '''if [ "$JRNL_RACER" = A ]; then
    : > "$HOME/writing-A"
    while [ ! -e "$HOME/finish-A" ]; do sleep 0.02; done
fi
printf '%s\\n' "$JRNL_TEST_NOW"
''')
        writers = []
        def stop():
            for writer in writers:
                if writer.poll() is None:
                    os.killpg(writer.pid, signal.SIGKILL)
                writer.communicate(timeout=5)
        self.addCleanup(stop)
        for name in ("A", "B"):
            env = dict(self.env, JRNL_RACER=name)
            writers.append(subprocess.Popen([str(SCRIPT), "Writer " + name], env=env,
                                            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                            start_new_session=True))
        for name in ("A", "B"):
            self.wait_for(lambda name=name: (self.home / ("ready-" + name)).exists())
        (self.home / "claim-A").touch()
        self.wait_for(lambda: (self.home / "writing-A").exists())
        (self.home / "claim-B").touch()
        stdout, stderr = writers[1].communicate(timeout=5)
        self.assertNotEqual(writers[1].returncode, 0, stdout + stderr)
        self.assertTrue((lock / str(writers[0].pid)).is_dir())
        self.assertEqual(self.log.read_bytes(), before)
        self.assertIn("File is busy", self.run_jrnl("Third writer", ok=False).stderr)
        (self.home / "finish-A").touch()
        stdout, stderr = writers[0].communicate(timeout=5)
        self.assertEqual(writers[0].returncode, 0, stdout + stderr)
        self.assertIn("Writer A", self.log.read_text())
        self.assertNotIn("Writer B", self.log.read_text())
        self.assertFalse(lock.exists())

    def test_setup_recovers_stale_config_lock(self):
        departed = subprocess.Popen(["true"])
        departed.wait(timeout=5)
        lock = self.home / ".zshrc.lock"
        (lock / str(departed.pid)).mkdir(parents=True)
        self.run_jrnl("--setup", input="\n")
        self.assertTrue((self.home / ".zshrc").is_file())
        self.assertFalse(lock.exists())

    def test_default_openers_are_called_with_one_path(self):
        self.run_jrnl("Entry")
        self.mock("uname", 'printf "%s\\n" "$JRNL_TEST_OS"\n')
        for os_name, executable, flag in (("Darwin", "open", "--open"), ("Linux", "xdg-open", "-o")):
            self.env["JRNL_TEST_OS"] = os_name
            self.mock(executable, 'test "$#" -eq 1 || exit 2\nprintf "opened: %s\\n" "$1"\n')
            self.assertEqual(self.run_jrnl(flag).stdout, f"opened: {self.log}\n")

    def start_zsh(self, term="xterm-256color", columns=160, history_options=""):
        self.run_jrnl("--setup", input="\n")
        session = ZshSession(self, term, columns)
        session.send("RPROMPT=''; typeset -gi _jrnl_test_prompt=0; "
                     'precmd() { (( ++_jrnl_test_prompt )); PS1="JRNL_READY_${_jrnl_test_prompt}> "; }; '
                     'HISTFILE="$HOME/history"; HISTSIZE=500; SAVEHIST=500; '
                     + (history_options + '; ' if history_options else '')
                     + 'bindkey -e; source "$HOME/.zshrc"')
        return session

    @unittest.skipUnless(shutil.which("zsh"), "zsh is needed for interactive integration")
    def test_real_zsh_literal_punctuation_and_history(self):
        session = self.start_zsh()
        session.send('source "$HOME/.zshrc"')
        entries = [
            "Why did <this> happen? {} # []., $foo | whatever",
            "Why? * <>{}#[] ., 'quoted' \"double\" can't $HOME $(touch PWNED) `touch PWNED2` ; & | ! !!",
            r"Keep  repeated   spaces, \backslashes\ and trailing spaces.  ",
            "café 日本語 🚀",
        ]
        for entry in entries:
            output = session.send("jrnl " + entry)
            self.assertIn("###### [13:26:21]\n\n" + entry + "\n\n", self.log.read_text(), output)
        session.send('fc -ln -4 > "$HOME/recent-history"')
        self.assertEqual((self.home / "recent-history").read_text().splitlines(),
                         ["jrnl " + entry for entry in entries])
        self.assertFalse((self.home / "PWNED").exists())
        self.assertFalse((self.home / "PWNED2").exists())
        entry = entries[1]
        session.send("jrnl " + entry)
        output = session.send("\x1b[A")
        self.assertIn("jrnl " + entry, output)
        self.assertEqual(self.log.read_text().count(entry), 3)
        session.send('fc -W')
        # Read saved history through zsh, which decodes its on-disk format.
        history = self.zsh('fc -R "$HOME/history"; fc -ln 1').stdout
        self.assertIn("jrnl café 日本語 🚀\n", history)
        self.assertIn("jrnl " + entry + "\n", history)
        self.assertNotIn(r"\jrnl", history)
        # Unrelated shell syntax still expands and executes normally.
        output = session.send('print -r -- "normal:$((2 + 3))" | cat')
        self.assertIn("normal:5", output)
        session.send('fc -ln -1 > "$HOME/other-history"')
        self.assertEqual((self.home / "other-history").read_text(),
                         'print -r -- "normal:$((2 + 3))" | cat\n')

    @unittest.skipUnless(shutil.which("zsh"), "zsh is needed for interactive integration")
    def test_real_zsh_display_stays_clean(self):
        for term, columns in (("xterm-256color", 160), ("xterm-256color", 40), ("dumb", 160)):
            with self.subTest(term=term, columns=columns):
                session = self.start_zsh(term, columns)
                entry = "This is the first test."
                output = session.send("jrnl " + entry)
                display = output.split("[✓]", 1)[0]
                self.assertNotIn("\\", display)
                # A wide terminal leaves the complete typed command on one row.
                if columns == 160:
                    self.assertIn("jrnl " + entry, display)
                self.assertIn("###### [13:26:21]\n\n" + entry, self.log.read_text())
                session.close()

    @unittest.skipUnless(shutil.which("zsh"), "zsh is needed for interactive integration")
    def test_real_zsh_flags_and_reconfiguration(self):
        session = self.start_zsh()
        self.mock("open", 'test "$#" -eq 1 || exit 2\nprintf "opened: %s\\n" "$1"\n')
        self.mock("uname", 'printf "Darwin\\n"\n')
        for flag in ("", "-h", "--help"):
            self.assertIn("Usage:", session.send("jrnl" + (" " + flag if flag else "")))
        for flag in ("-V", "--version"):
            self.assertIn("jrnl 0.1.2a", session.send("jrnl " + flag))
        self.assertIn(str(self.log), session.send("jrnl --check"))
        for flag in ("--open", "-o"):
            self.assertIn(f"opened: {self.log}", session.send("jrnl " + flag))
        session.send("jrnl -- --help")
        task = "- [ ] ah now I get it! A `-` at sentence beginning needs a `--` to work and then the desired `-`."
        session.send("jrnl -- " + task)
        self.assertIn("###### [13:26:21]\n\n" + task + "\n\n", self.log.read_text())
        self.assertIn("###### [13:26:21]\n\n--help", self.log.read_text())
        output = session.send("jrnl --show").replace("\r\n", "\n")
        self.assertIn(self.log.read_text(), output)
        before = self.log.read_bytes()
        for command, error in (("jrnl --cat", "Unknown option"),
                               ("jrnl --typo", "Unknown option"),
                               ("jrnl --show unexpected", "Unknown option"),
                               ("jrnl --", "Entry cannot be empty")):
            self.assertIn(error, session.send(command))
            self.assertEqual(self.log.read_bytes(), before)
        # The wrapper imports the new path into this same shell after setup.
        session.write("jrnl --setup\n")
        session.expect(b"Journal file path [", suffix=False)
        new_log = self.home / "second $journal.md"
        session.send(str(new_log))
        session.send("jrnl After reconfiguration?")
        self.assertIn("After reconfiguration?", new_log.read_text())
        self.assertIn(str(new_log), session.send("jrnl --check"))
        self.assertEqual(self.log.read_bytes(), before)

    @unittest.skipUnless(shutil.which("zsh"), "zsh is needed for interactive integration")
    def test_real_zsh_keeps_other_hooks_and_multiline_commands(self):
        session = self.start_zsh()
        session.send('autoload -Uz add-zsh-hook add-zle-hook-widget; '
                     'other_history() { print -r -- "$1" >> "$HOME/other-hook"; }; '
                     'other_finish() { print -r -- ran >> "$HOME/finish-hook"; }; '
                     'zle -N other_finish; add-zle-hook-widget line-finish other_finish; '
                     'add-zsh-hook zshaddhistory other_history; source "$HOME/.zshrc"; '
                     "PS2='CONTINUE> '")
        session.send('jrnl Hook test $literal | text')
        before = self.log.read_bytes()
        output = session.send('print -r -- "other:$((3 + 4))"')
        self.assertIn("other:7", output)
        self.assertIn('print -r -- "other:$((3 + 4))"', (self.home / "other-hook").read_text())
        self.assertEqual((self.home / "finish-hook").read_text(), "ran\nran\n")
        session.write("print -r -- 'first line\n")
        session.expect(b"CONTINUE> ")
        output = session.send("jrnl $HOME | still ordinary quoted text'")
        self.assertIn("first line\r\njrnl $HOME | still ordinary quoted text", output)
        self.assertEqual(self.log.read_bytes(), before)

    @unittest.skipUnless(shutil.which("zsh"), "zsh is needed for interactive integration")
    def test_real_zsh_history_modes_and_ignore_space(self):
        for options in ("setopt INC_APPEND_HISTORY", "setopt SHARE_HISTORY", "setopt HIST_IGNORE_SPACE"):
            with self.subTest(options=options):
                session = self.start_zsh(history_options=options)
                session.send("jrnl Human readable $text | and punctuation!")
                session.send(" jrnl Hidden from history")
                session.send('fc -W')
                history = (self.home / "history").read_text()
                self.assertIn("jrnl Human readable $text | and punctuation!\n", history)
                self.assertNotIn(r"\jrnl", history)
                if "HIST_IGNORE_SPACE" in options:
                    self.assertNotIn("jrnl Hidden from history", history)
                self.assertIn("Hidden from history", self.log.read_text())
                session.close()
                (self.home / "history").unlink()


class ZshSession:
    """A real ZLE session with numbered prompts and an isolated test home."""

    def __init__(self, test, term, columns):
        self.test = test
        self.fd, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 30, columns, 0, 0))
        env = dict(test.env, TERM=term, NO_COLOR="1")
        self.shell = subprocess.Popen(["zsh", "-dfi"], cwd=test.home, env=env,
                                      stdin=slave, stdout=slave, stderr=slave,
                                      start_new_session=True)
        os.close(slave)
        self.prompt_number = 0
        test.addCleanup(self.close)

    def close(self):
        if self.fd is None:
            return
        self.shell.kill()
        self.shell.wait(timeout=2)
        os.close(self.fd)
        self.fd = None

    def write(self, text):
        os.write(self.fd, text.encode())

    def expect(self, expected, suffix=True):
        output = b""
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            ready, _, _ = select.select([self.fd], [], [], 0.1)
            if ready:
                output += os.read(self.fd, 65536)
                plain = re.sub(rb"\x1b\[[0-9;?]*[A-Za-z]", b"", output)
                if (plain.endswith(expected) if suffix else expected in plain):
                    return output.decode(errors="replace")
        self.test.fail("zsh did not produce " + repr(expected) + ": " + repr(output))

    def send(self, line):
        self.prompt_number += 1
        self.write(line + "\n")
        return self.expect(f"JRNL_READY_{self.prompt_number}> ".encode())


if __name__ == "__main__":
    unittest.main(verbosity=2)
