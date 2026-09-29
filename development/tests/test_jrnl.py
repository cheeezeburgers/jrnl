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

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "jrnl.sh"
VERSION = re.search(r"^VERSION=(\S+)$", SCRIPT.read_text(), re.MULTILINE).group(1)


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="jrnl-test-")
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name).resolve()
        self.script = SCRIPT
        self.installed = self.home / ".local/bin/jrnl"
        self.integration = self.home / ".local/share/jrnl/jrnl.zsh"
        self.selector = self.home / ".local/share/jrnl/clack-select.sh"
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

    def setup_input(self, path=None):
        path = Path(path or self.log)
        return f"j\n{path.parent}\njj\n{path.name}\n"

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
            self.assertEqual(self.run_jrnl(flag).stdout, f"jrnl {VERSION}\n")
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
        return ("\n" + first + f"    was written to {self.log.name}\n"
                f"    in {self.log.parent}/\n" + hint)

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

    def test_setup_defaults_create_documents_and_jrnl(self):
        self.env.pop("JRNL_FILE")
        self.assertFalse((self.home / "Documents").exists())
        result = self.run_jrnl("--setup", input="\n\n")
        target = self.home / "Documents/jrnl.md"
        self.assertTrue(target.is_file())
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertIn("Where should your journal live?", result.stderr)
        self.assertIn("Enter the name for your jrnl-file:", result.stderr)
        self.assertIn("Journal path and file name: ~/Documents/jrnl.md", result.stdout)
        self.assertIn(str(target), self.zsh('source "$HOME/.zshrc"; jrnl --check').stdout)
        for instruction in ("↑", "↓", "j/k", "arrow"):
            self.assertNotIn(instruction, result.stderr)
        before = (self.home / ".zshrc").stat().st_mtime_ns
        self.run_jrnl("--setup", input="\n\n")
        self.assertEqual((self.home / ".zshrc").stat().st_mtime_ns, before)
        self.assertFalse((self.home / ".zshrc.jrnl.bak").exists())

    def test_setup_location_and_filename_choices(self):
        for location, location_keys in (("", "k\n"), ("Documents", "kj\n")):
            for name, filename_keys in (("jrnl.md", "\n"), ("journal.md", "k\n"),
                                        ("devlog.md", "j\n")):
                with self.subTest(location=location, name=name):
                    self.run_jrnl("--setup", input=location_keys + filename_keys)
                    target = self.home / location / name
                    self.assertTrue(target.is_file())
                    self.assertIn(str(target), self.zsh('source "$HOME/.zshrc"; jrnl --check').stdout)

    def test_custom_location_and_filename_suffixes(self):
        for name in ("notes", "notes.md", "NOTES.MD", "mixed.Md", "mixed.mD", "devlog",
                     "engineering-log", "literal $name `code` \\ !"):
            with self.subTest(name=name):
                directory = "~/new directory/nested"
                self.run_jrnl("--setup", input=f"j\n{directory}\njj\n{name}\n")
                expected = name if name.lower().endswith(".md") else name + ".md"
                target = self.home / "new directory/nested" / expected
                self.assertTrue(target.is_file())
                self.assertIn(str(target), self.zsh('source "$HOME/.zshrc"; jrnl --check').stdout)
                self.assertFalse(Path(str(target) + ".md").exists())

    def test_path_logic_without_menu_rendering(self):
        # Source the pure path helper; it must not create files or evaluate input.
        for name, expected in (("notes", "notes.md"), ("NOTES.MD", "NOTES.MD"),
                               ("notes.md", "notes.md"), ("x.Md", "x.Md"),
                               ("notes.txt", "notes.txt"), ("  notes.md  ", "notes.md"),
                               ("  notes  ", "notes.md"), ("notes  today.txt ", "notes  today.txt")):
            result = subprocess.run(["/bin/bash", "-c", 'source "$1"; journal_path "$2" "$3"',
                                     "test", str(SCRIPT), str(self.home / "missing"), name],
                                    env=self.env, text=True, capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, str(self.home / "missing" / expected) + "\n")
        self.assertFalse((self.home / "missing").exists())

    def test_custom_filename_suffixes_and_whitespace(self):
        cases = (("dev-journal", "dev-journal.md"),
                 ("dev-journal.md", "dev-journal.md"),
                 ("DEV-JOURNAL.MD", "DEV-JOURNAL.MD"),
                 ("dev-journal.txt", "dev-journal.txt"),
                 ("  dev-journal  ", "dev-journal.md"),
                 ("dev-journal.md ", "dev-journal.md"),
                 ("  DEV-JOURNAL.MD  ", "DEV-JOURNAL.MD"),
                 ("\t dev-journal.txt \t", "dev-journal.txt"),
                 ("  dev  journal  ", "dev  journal.md"),
                 ("  dev  journal.md  ", "dev  journal.md"),
                 ("archive.tar.gz", "archive.tar.gz"),
                 (".journal", ".journal.md"),
                 (".journal.txt", ".journal.txt"))
        for index, (name, expected) in enumerate(cases):
            with self.subTest(name=name):
                directory = self.home / f"suffix-{index}"
                self.run_jrnl("--setup", input=f"j\n{directory}\njj\n{name}\n")
                self.assertEqual([p.name for p in directory.iterdir()], [expected])
                self.assertIn(str(directory / expected),
                              self.zsh('source "$HOME/.zshrc"; jrnl --check').stdout)

    def test_setup_retries_empty_and_invalid_locations(self):
        file = self.home / "not-a-directory"
        file.write_text("keep")
        loop = self.home / "loop"
        loop.symlink_to(loop)
        invalid = (("", "The directory path must be a nonempty single line."),
                   (" \t ", "The directory path must be a nonempty single line."),
                   ("bad\rpath", "The directory path must be a nonempty single line."),
                   (str(file), "Please choose a directory."),
                   (str(loop), "Too many symlinks:"))
        for location, message in invalid:
            with self.subTest(location=location):
                result = self.run_jrnl("--setup", input=f"j\n{location}\nj\n{self.log.parent}\n\n")
                self.assertIn(message, result.stderr)
                self.assertEqual(result.stderr.count("Where should your journal live?"), 2)
                self.assertEqual(result.stderr.count("Enter the name for your jrnl-file:"), 1)
                target = self.log.parent / "jrnl.md"
                self.assertTrue(target.is_file())
                self.assertIn(str(target), self.zsh('source "$HOME/.zshrc"; jrnl --check').stdout)
        self.assertEqual(file.read_text(), "keep")
        self.assertTrue(loop.is_symlink())

    def test_setup_retries_empty_and_invalid_filenames_in_chosen_location(self):
        directory = self.home / "chosen location"
        directory.mkdir()
        (directory / "existing").mkdir()
        (directory / "normalized.md").mkdir()
        (directory / "link.md").symlink_to(directory / "existing")
        invalid = ("", " \t ", ".", "..", "~", "nested/file", "file/", "/tmp/file", "bad\rname")
        directories = ("existing", "normalized", "link.md", "  existing  ")
        for index, name in enumerate(invalid + directories):
            with self.subTest(name=name):
                target = directory / f"recovered-{index}.md"
                result = self.run_jrnl("--setup", input=f"j\n{directory}\njj\n{name}\njj\n{target.name}\n")
                message = ("The filename resolves to a directory." if name in directories else
                           "Please enter a filename without a directory path.")
                self.assertIn(message, result.stderr)
                self.assertEqual(result.stderr.count("Where should your journal live?"), 1)
                self.assertEqual(result.stderr.count("Enter the name for your jrnl-file:"), 2)
                self.assertTrue(target.is_file())
                self.assertIn(str(target), self.zsh('source "$HOME/.zshrc"; jrnl --check').stdout)
        self.assertFalse((self.home / "Documents").exists())
        self.assertTrue((directory / "link.md").is_symlink())

    def test_custom_relative_and_symlink_paths(self):
        directory = self.home / "actual"
        directory.mkdir()
        link = self.home / "linked"
        link.symlink_to(directory)
        target = directory / "real.md"
        target.write_text("Keep me\n")
        target.chmod(0o640)
        (directory / "alias.md").symlink_to(target)
        relative = os.path.relpath(link, ROOT)
        self.run_jrnl("--setup", input=f"j\n{relative}\njj\nalias.md\n")
        self.assertEqual(target.read_text(), "Keep me\n")
        self.assertEqual(target.stat().st_mode & 0o777, 0o640)
        self.assertTrue((directory / "alias.md").is_symlink())
        self.assertIn(str(target), self.zsh('source "$HOME/.zshrc"; jrnl --check').stdout)

    def test_setup_rejects_invalid_directories_and_filenames(self):
        directory = self.home / "folder"
        directory.mkdir()
        (directory / "existing").mkdir()
        (directory / "normalized.md").mkdir()
        (directory / "link.md").symlink_to(directory / "existing")
        file = self.home / "not-a-directory"
        file.write_text("keep")
        for location in ("", " ", str(file), "bad\rpath"):
            with self.subTest(location=location):
                self.run_jrnl("--setup", input=f"j\n{location}\n\n", ok=False)
        for name in ("", " ", ".", "..", "~", "nested/file", "file/", "/tmp/file",
                     "bad\rname", "existing", "normalized", "link.md"):
            with self.subTest(name=name):
                self.run_jrnl("--setup", input=f"j\n{directory}\njj\n{name}\n", ok=False)
        self.assertFalse((self.home / ".zshrc").exists())
        self.assertFalse(self.installed.exists())
        self.assertEqual(file.read_text(), "keep")

    def test_setup_eof_and_cancel_at_each_step_do_not_write(self):
        for keys in ("", "\x03", "j\n", "\n", "\n\x03", "\njj\n",
                     "j\n\n", "j\n\n\x03", "\njj\n\n", "\njj\nnested/file\n\x03"):
            with self.subTest(keys=keys):
                self.assertIn("cancelled", self.run_jrnl("--setup", input=keys, ok=False).stderr)
                self.assertFalse((self.home / "Documents").exists())
                self.assertFalse((self.home / ".zshrc").exists())
                self.assertFalse((self.home / ".local").exists())

    def test_selector_navigation_and_wraparound(self):
        for keys, expected in (("\n", "Documents"), ("k\n", "Home"), ("K\n", "Home"),
                               ("j\n", "Other"), ("J\n", "Other"), ("kk\n", "Other"),
                               ("jj\n", "Home"), ("\x1b[A\n", "Home"),
                               ("\x1b[B\n", "Other"), ("\x1bOA\n", "Home"),
                               ("\x1bOB\n", "Other")):
            with self.subTest(keys=keys):
                result = subprocess.run(["/bin/bash", "-c", 'set -eu; source "$1"; '
                                         'clack_select Location 1 Home Documents Other',
                                         "test", str(ROOT / "vendor/clack-bash/select.sh")],
                                        env=self.env, input=keys, text=True, capture_output=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, expected)
                self.assertNotIn("\x1b", result.stderr)

    def test_installer_protects_selector_and_checks_missing_source(self):
        self.selector.parent.mkdir(parents=True)
        for kind in ("file", "directory", "symlink"):
            with self.subTest(kind=kind):
                victim = self.home / "unrelated"
                victim.write_text("keep me")
                if kind == "file":
                    self.selector.write_text("unrelated selector")
                elif kind == "directory":
                    self.selector.mkdir()
                else:
                    self.selector.symlink_to(victim)
                for args in ((), ("--dry-run",)):
                    self.assertIn("Refusing to replace", self.install(*args, ok=False).stderr)
                    self.assertFalse(self.installed.exists())
                    self.assertFalse(self.integration.exists())
                    self.assertEqual(victim.read_text(), "keep me")
                if kind == "directory":
                    self.selector.rmdir()
                else:
                    self.selector.unlink()
        repo = self.home / "incomplete"
        repo.mkdir()
        for name in ("jrnl.sh", "jrnl.zsh", "install.sh"):
            shutil.copy2(ROOT / name, repo / name)
        self.assertIn("Missing installation files", self.install(root=repo, ok=False).stderr)
        self.assertFalse(self.installed.exists())

    def test_installed_setup_reports_missing_selector(self):
        self.install()
        self.selector.unlink()
        self.script = self.installed
        self.assertIn("Missing setup selector", self.run_jrnl("--setup", input="\n\n", ok=False).stderr)
        # Unrelated flags and configured logging do not load the selector.
        self.run_jrnl("--help")
        self.run_jrnl("Still logs")
        self.install()
        self.run_jrnl("--setup", input="\n\n")

    def test_real_terminal_readline_completion(self):
        session = self.start_zsh()
        directory = self.home / "vscode-projects"
        directory.mkdir()
        journal = directory / "engineering-log.md"
        journal.write_text("Keep existing content\n")
        session.write("jrnl --setup\n")
        session.expect(b"Location", suffix=False)
        session.write("j\n")
        session.expect(b"Directory path: ")
        session.write("~/vscode-pro\t")
        session.expect(b"vscode-projects/", suffix=False)
        session.write("\n")
        session.expect(b"Filename", suffix=False)
        session.write("jj\n")
        session.expect(b"Filename: ")
        session.write("engineering-l\t")
        session.expect(b"engineering-log.md", suffix=False)
        session.send("")
        self.assertIn(str(journal), session.send("jrnl --check"))
        self.assertEqual(journal.read_text(), "Keep existing content\n")

    def test_real_terminal_defaults_and_cancellation(self):
        session = self.start_zsh()
        rc = self.home / ".zshrc"
        original = rc.read_bytes()
        session.write("jrnl --setup\n")
        menu = session.expect(b"Other", suffix=False)
        self.assertIn("Location", menu)
        self.assertRegex(menu, r"[❯>] Documents")
        session.prompt_number += 1
        session.write("\x03")
        output = session.expect(f"JRNL_READY_{session.prompt_number}> ".encode())
        self.assertIn("\x1b[?25h", output)
        self.assertEqual(rc.read_bytes(), original)
        self.assertFalse((self.home / "Documents").exists())
        session.write("jrnl --setup\n")
        session.expect(b"Other", suffix=False)
        session.write("\n")
        menu = session.expect(b"Other", suffix=False)
        self.assertIn("Filename", menu)
        self.assertRegex(menu, r"[❯>] jrnl.md")
        session.send("")
        self.assertTrue((self.home / "Documents/jrnl.md").is_file())

    def test_real_terminal_setup_retries_current_step(self):
        session = self.start_zsh()
        rc = self.home / ".zshrc"
        original = rc.read_bytes()
        directory = self.home / "chosen location"
        directory.mkdir()
        (directory / "existing").mkdir()
        file = self.home / "not-a-directory"
        file.write_text("keep")
        session.write("jrnl --setup\n")
        session.expect(b"Other", suffix=False)
        for value, message in (("", "nonempty single line"), (str(file), "Please choose a directory")):
            session.write("j\n")
            session.expect(b"Directory path: ")
            session.write(value + "\n")
            menu = session.expect(b"Other", suffix=False)
            self.assertIn(message, menu)
            self.assertIn("Location", menu)
            self.assertNotIn("Filename", menu)
            self.assertEqual(rc.read_bytes(), original)
        session.write("j\n")
        session.expect(b"Directory path: ")
        session.write(str(directory) + "\n")
        session.expect(b"Other", suffix=False)
        for value, message in (("", "filename without a directory path"),
                               ("existing", "filename resolves to a directory")):
            session.write("jj\n")
            session.expect(b"Filename: ")
            session.write(value + "\n")
            menu = session.expect(b"Other", suffix=False)
            self.assertIn(message, menu)
            self.assertIn("Filename", menu)
            self.assertNotIn("Location", menu)
            self.assertEqual(rc.read_bytes(), original)
        session.write("jj\n")
        session.expect(b"Filename: ")
        session.send("  dev  journal.txt  ")
        target = directory / "dev  journal.txt"
        self.assertTrue(target.is_file())
        self.assertIn(str(target), session.send("jrnl --check"))
        self.assertEqual(file.read_text(), "keep")

    def test_real_terminal_cancellation_after_validation_errors(self):
        session = self.start_zsh()
        rc = self.home / ".zshrc"
        original = rc.read_bytes()
        for stage in ("location selector", "location input", "filename selector", "filename input"):
            with self.subTest(stage=stage):
                session.write("jrnl --setup\n")
                session.expect(b"Other", suffix=False)
                if stage.startswith("filename"):
                    session.write("\n")
                    session.expect(b"Other", suffix=False)
                keys = "jj\n" if stage.startswith("filename") else "j\n"
                prompt = b"Filename: " if stage.startswith("filename") else b"Directory path: "
                session.write(keys)
                session.expect(prompt)
                session.write("\n")
                session.expect(b"Other", suffix=False)
                if stage.endswith("input"):
                    session.write(keys)
                    session.expect(prompt)
                session.prompt_number += 1
                session.write("\x03")
                session.expect(f"JRNL_READY_{session.prompt_number}> ".encode())
                self.assertEqual(rc.read_bytes(), original)
                self.assertFalse((self.home / "Documents").exists())

    def test_setup_preserves_config_and_is_repeatable(self):
        rc = self.home / ".zshrc"
        original = "# Keep this\nexport EXISTING=value\n"
        rc.write_text(original)
        path = self.home / "O'Brien $notes [work]" / "diary"
        self.run_jrnl("--setup", input=self.setup_input(path))
        configured = Path(str(path) + ".md")
        self.assertTrue(configured.is_file())
        self.assertEqual((self.home / ".zshrc.jrnl.bak").read_text(), original)
        self.assertTrue(rc.read_text().startswith(original))
        first_config = rc.read_bytes()
        first_stat = rc.stat()
        self.run_jrnl("--setup", input=self.setup_input(path))
        self.assertEqual(rc.read_bytes(), first_config)
        self.assertEqual(rc.stat().st_mtime_ns, first_stat.st_mtime_ns)
        self.assertEqual((self.home / ".zshrc.jrnl.bak").read_text(), original)
        self.assertEqual(rc.read_text().count("# >>> jrnl >>>"), 1)
        self.assertEqual(rc.read_text().count("export JRNL_FILE="), 1)
        self.assertNotIn(str(ROOT), rc.read_text())
        self.assertTrue(self.installed.is_file())
        self.assertTrue(self.integration.is_file())
        self.assertTrue(self.selector.is_file())
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
        self.run_jrnl("--setup", input=self.setup_input())
        self.assertTrue(rc.read_text().startswith(before))
        self.assertTrue(rc.read_text().endswith(after))
        self.assertNotIn("/old/repo", rc.read_text())
        self.assertEqual(rc.stat().st_mode & 0o777, 0o640)
        self.assertEqual((self.home / ".zshrc.jrnl.bak").read_text(), original)

    def test_installer_dry_run_and_reinstall(self):
        original = {p.relative_to(self.home): p.read_bytes() for p in self.home.rglob("*") if p.is_file()}
        preview = self.install("--dry-run").stdout
        self.assertIn("No changes made", preview)
        self.assertIn(str(self.selector), preview)
        self.assertFalse((self.home / ".local").exists())
        self.assertEqual(original, {p.relative_to(self.home): p.read_bytes() for p in self.home.rglob("*") if p.is_file()})
        self.assertIn("Usage:", self.install("--help").stdout)
        self.install("--dry-run", "extra", ok=False)
        self.install("--typo", ok=False)
        result = self.install()
        self.assertIn(f"jrnl {VERSION}", result.stdout)
        self.assertIn("not on PATH", result.stdout)
        self.assertIn(str(self.installed), result.stdout)
        self.assertFalse((self.home / ".zshrc").exists())
        self.assertFalse(self.log.exists())
        self.assertEqual(self.installed.read_bytes(), SCRIPT.read_bytes())
        self.assertEqual(self.integration.read_bytes(), (ROOT / "jrnl.zsh").read_bytes())
        self.assertEqual(self.installed.stat().st_mode & 0o777, 0o755)
        self.assertEqual(self.integration.stat().st_mode & 0o777, 0o644)
        self.assertEqual(self.selector.stat().st_mode & 0o777, 0o644)
        self.assertEqual(self.selector.read_bytes(), (ROOT / "vendor/clack-bash/select.sh").read_bytes())
        self.assertIn("Permission is hereby granted", self.selector.read_text())
        # An older installed copy is safely replaced; dry-run does not replace it.
        self.installed.write_text(self.installed.read_text().replace(f"VERSION={VERSION}", "VERSION=0.0.1a"))
        self.selector.write_text(self.selector.read_text() + "\n# older copy\n")
        old_selector = self.selector.read_bytes()
        old = self.installed.read_bytes()
        self.install("--dry-run")
        self.assertEqual(self.installed.read_bytes(), old)
        self.assertEqual(self.selector.read_bytes(), old_selector)
        self.install()
        self.assertEqual(self.selector.read_bytes(), (ROOT / "vendor/clack-bash/select.sh").read_bytes())
        self.assertEqual(self.installed.read_bytes(), SCRIPT.read_bytes())

    def test_installed_files_survive_repo_move_and_removal(self):
        repo = self.home / "checkout with 'quotes' $ []"
        repo.mkdir()
        for name in ("jrnl.sh", "jrnl.zsh", "install.sh"):
            shutil.copy2(ROOT / name, repo / name)
        shutil.copytree(ROOT / "vendor", repo / "vendor")
        self.install(root=repo)
        self.script = self.installed
        self.run_jrnl("--setup", input=self.setup_input())
        moved = repo.with_name("moved checkout")
        repo.rename(moved)
        self.run_jrnl("Works after move")
        shutil.rmtree(moved)
        self.run_jrnl("Works after removal")
        self.run_jrnl("--setup", input=self.setup_input())
        for flag in ("-h", "--help", "-V", "--version", "--check", "--show"):
            self.run_jrnl(flag)
        self.run_jrnl("--", "--help")
        self.mock("open", 'printf "opened: %s\\n" "$1"\n')
        for flag in ("-o", "--open"):
            self.assertIn(str(self.log), self.run_jrnl(flag).stdout)
        result = self.zsh('source "$HOME/.zshrc"; source "$HOME/.zshrc"; jrnl "Via zsh"; command jrnl --version; print -r -- "$PATH"')
        self.assertIn(f"jrnl {VERSION}", result.stdout)
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
        self.run_jrnl("--setup", input=self.setup_input())
        result = self.zsh('''source "$HOME/.zshrc"
# Recreate the prior wrapper: same body, but it invoked bash on a repo script.
functions[jrnl]=${functions[jrnl]/command /command bash }
unset _JRNL_WRAPPER
JRNL_SCRIPT=/removed-checkout/jrnl.sh
source "$HOME/.zshrc"
jrnl --version
''')
        self.assertEqual(result.stdout, f"jrnl {VERSION}\n")
        self.assertEqual(result.stderr, "")

    def test_setup_with_shell_sensitive_home_and_journal_paths(self):
        special_home = self.home / "home 'quoted' $notes [work]"
        special_home.mkdir()
        self.env["HOME"] = str(special_home)
        journal = special_home / "$(touch PWNED) `touch PWNED2` \\ !.md"
        self.run_jrnl("--setup", input=self.setup_input(journal))
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
                self.run_jrnl("--setup", input=self.setup_input(), ok=False)
                self.assertEqual(rc.read_text(), original)
                self.assertEqual(backup.read_text(), "previous backup")
        rc.write_text("# original\n")
        backup.unlink()
        victim = self.home / "keep-backup-target"
        victim.write_text("keep")
        backup.symlink_to(victim)
        self.run_jrnl("--setup", input=self.setup_input(), ok=False)
        self.assertEqual(rc.read_text(), "# original\n")
        self.assertEqual(victim.read_text(), "keep")

    def test_missing_config_prompts_and_keeps_first_entry(self):
        self.env.pop("JRNL_FILE")
        result = self.run_jrnl("First entry", input=self.setup_input("~/new folder/diary.md"))
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
        self.run_jrnl("--setup", input=self.setup_input(), ok=False)
        self.assertEqual(rc.read_text(), original)
        self.assertFalse(Path(str(rc) + ".lock").exists())

    def test_zdotdir_and_symlinked_configuration(self):
        config_dir = self.home / "zsh config"
        config_dir.mkdir()
        self.env["ZDOTDIR"] = str(config_dir)
        target = self.home / "actual-zshrc"
        target.write_text("# dotfiles\n")
        (config_dir / ".zshrc").symlink_to(target)
        self.run_jrnl("--setup", input=self.setup_input())
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
        self.run_jrnl("--setup", input=self.setup_input())
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
        self.run_jrnl("--setup", input=self.setup_input())
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
            self.assertIn(f"jrnl {VERSION}", session.send("jrnl " + flag))
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
        session.expect(b"Location", suffix=False)
        session.write("k\n")
        session.expect(b"Filename", suffix=False)
        session.write("jj\n")
        session.expect(b"Filename: ")
        new_log = self.home / "second $journal.md"
        session.send(new_log.name)
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
                                      start_new_session=True,
                                      preexec_fn=lambda: fcntl.ioctl(0, termios.TIOCSCTTY, 0))
        os.close(slave)
        self.prompt_number = 0
        test.addCleanup(self.close)

    def close(self):
        if self.fd is None:
            return
        self.shell.kill()
        # Close the controlling terminal before waiting (macOS tty teardown).
        os.close(self.fd)
        self.fd = None
        self.shell.wait(timeout=5)

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
