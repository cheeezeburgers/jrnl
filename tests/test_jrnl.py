#!/usr/bin/env python3
"""Integration tests using temporary homes; never changes your shell config."""
import os
from pathlib import Path
import pty
import re
import select
import shlex
import shutil
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "jrnl.sh"


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="jrnl-test-")
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.log = self.home / "notes with spaces" / "engineering.md"
        self.bin = self.home / "bin"
        self.bin.mkdir()
        self.env = os.environ.copy()
        for key in ("ZDOTDIR", "BASH_ENV", "ENV", "JRNL_FILE"):
            self.env.pop(key, None)
        self.env.update(HOME=str(self.home), PATH=f"{self.bin}:{os.environ['PATH']}",
                        JRNL_FILE=str(self.log), JRNL_TEST_NOW="2026-09-26 13:26:21")
        self.mock("date", 'printf "%s\\n" "$JRNL_TEST_NOW"\n')

    def mock(self, name, body):
        path = self.bin / name
        path.write_text("#!/bin/sh\n" + body)
        path.chmod(0o755)

    def run_jrnl(self, *args, input=None, ok=True):
        result = subprocess.run(["bash", str(SCRIPT), *args], env=self.env,
                                input=input, text=True, capture_output=True, timeout=10)
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def test_help_version_and_invalid_input(self):
        for flag in ("-h", "--help"):
            self.assertIn("Usage:", self.run_jrnl(flag).stdout)
        for flag in ("-V", "--version"):
            self.assertEqual(self.run_jrnl(flag).stdout, "jrnl 1.0.0\n")
        self.run_jrnl("--typo", ok=False)
        self.run_jrnl("--cat", "unexpected", ok=False)
        self.run_jrnl("--", ok=False)
        self.run_jrnl("   ", ok=False)
        self.run_jrnl("two\nlines", ok=False)
        self.assertFalse(self.log.exists())

    def test_newest_entries_and_days_first(self):
        first = self.run_jrnl("Investigated", "strange network traffic today.")
        self.assertIn(str(self.log), first.stdout)
        self.assertIn("[13:26:21] Investigated strange network traffic today.", first.stdout)
        self.env["JRNL_TEST_NOW"] = "2026-09-26 14:00:00"
        self.run_jrnl("Second entry")
        self.env["JRNL_TEST_NOW"] = "2026-09-27 09:00:00"
        self.run_jrnl("Next day")
        self.assertEqual(self.log.read_text(),
                         "## 2026-09-27\n\n[09:00:00] Next day\n\n"
                         "## 2026-09-26\n\n[14:00:00] Second entry\n"
                         "[13:26:21] Investigated strange network traffic today.\n\n")
        self.env["JRNL_TEST_NOW"] = "2026-09-26 15:00:00"
        self.run_jrnl("Back to an existing date")
        self.assertEqual(self.log.read_text().count("## 2026-09-26"), 1)
        self.assertIn("## 2026-09-26\n\n[15:00:00] Back", self.log.read_text())

    def test_literal_text_cat_and_check(self):
        entry = r"Why? <>{}#[] ., %s \\n $HOME $(echo nope) `whoami` & | ; ! café"
        self.run_jrnl(entry)
        self.run_jrnl("--", "--help")
        contents = self.log.read_text()
        self.assertIn(entry, contents)
        self.assertIn("[13:26:21] --help", contents)
        self.assertEqual(self.run_jrnl("--cat").stdout, contents)
        self.assertIn(str(self.log), self.run_jrnl("--check").stdout)

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
        self.run_jrnl("--setup", input=str(path) + "\n")
        self.assertEqual(rc.read_text().count("# >>> jrnl >>>"), 1)
        self.assertEqual(rc.read_text().count("export JRNL_FILE="), 1)
        if shutil.which("zsh"):
            result = subprocess.run(["zsh", "-dfc", 'source "$HOME/.zshrc"; jrnl --check'],
                                    env=self.env, text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(str(configured), result.stdout)

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

    def test_default_openers_are_called_with_one_path(self):
        self.run_jrnl("Entry")
        self.mock("uname", 'printf "%s\\n" "$JRNL_TEST_OS"\n')
        for os_name, executable, flag in (("Darwin", "open", "--open"), ("Linux", "xdg-open", "-o")):
            self.env["JRNL_TEST_OS"] = os_name
            self.mock(executable, 'test "$#" -eq 1 || exit 2\nprintf "opened: %s\\n" "$1"\n')
            self.assertEqual(self.run_jrnl(flag).stdout, f"opened: {self.log}\n")

    @unittest.skipUnless(shutil.which("zsh"), "zsh is needed for interactive integration")
    def test_real_zsh_literal_punctuation_and_history(self):
        fd, slave = pty.openpty()
        env = self.env.copy()
        env.update(TERM="dumb")
        shell = subprocess.Popen(["zsh", "-dfi"], cwd=self.home, env=env,
                                 stdin=slave, stdout=slave, stderr=slave,
                                 start_new_session=True)
        os.close(slave)
        def close_shell():
            shell.terminate()
            try:
                shell.wait(timeout=2)
            except subprocess.TimeoutExpired:
                shell.kill()
                shell.wait(timeout=2)
            finally:
                os.close(fd)
        self.addCleanup(close_shell)
        def expect_prompt():
            output = b""
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                ready, _, _ = select.select([fd], [], [], 0.1)
                if ready:
                    output += os.read(fd, 65536)
                    if re.sub(rb"\x1b\[[0-9;?]*[A-Za-z]", b"", output).endswith(b"JRNL_READY> "):
                        return output.decode(errors="replace")
            self.fail("zsh did not return to prompt: " + output.decode(errors="replace"))
        def send(line):
            os.write(fd, line.encode() + b"\n")
            return expect_prompt()
        send("PS1='JRNL_READY> '; RPROMPT=''; bindkey -e; source " + shlex.quote(str(ROOT / "jrnl.zsh")))
        entry = "Why? <>{}#[] ., 'quoted' can't $HOME $(touch PWNED) `touch PWNED2` ; & | !"
        send("jrnl " + entry)
        self.assertIn("[13:26:21] " + entry, self.log.read_text())
        self.assertFalse((self.home / "PWNED").exists())
        self.assertFalse((self.home / "PWNED2").exists())
        os.write(fd, b"\x1b[A\n")
        expect_prompt()
        self.assertEqual(self.log.read_text().count(entry), 2)
        self.assertIn(str(self.log), send("jrnl --check"))
        send("jrnl -- --help")
        self.assertIn("[13:26:21] --help", self.log.read_text())
        self.assertIn("unrelated command", send("print -r -- 'unrelated command'"))
        # The wrapper imports the new path into this same shell after setup.
        os.write(fd, b"jrnl --setup\n")
        time.sleep(0.2)
        new_log = self.home / "second $journal.md"
        os.write(fd, str(new_log).encode() + b"\n")
        expect_prompt()
        send("jrnl After reconfiguration?")
        self.assertIn("After reconfiguration?", new_log.read_text())


if __name__ == "__main__":
    unittest.main(verbosity=2)
