# jrnl

A tiny engineering diary.

![jrnl-hero-img](assets/jrnl-hero-img.png)

Version **0.1.2a**. Tested on macOS with its bundled Bash 3.2, zsh and standard command-line tools. (Python 3 is only needed for tests).

## Install

From the checkout, run:

```sh
./install.sh
~/.local/bin/jrnl --setup
source "${ZDOTDIR:-$HOME}/.zshrc"
```

The installer copies the Bash executable to `~/.local/bin/jrnl` and the zsh integration to `~/.local/share/jrnl/jrnl.zsh`. You can then move or delete the checkout. To update, re-run `./install.sh` from the new checkout and source `"${ZDOTDIR:-$HOME}/.zshrc"` again; `./install.sh --dry-run` checks and previews installation without changing files. Installation does not download anything or edit shell configuration, and refuses to replace unrelated files.

Setup prompts for a journal path, creates missing folders and the `.md` file, and adds a managed block to `${ZDOTDIR:-$HOME}/.zshrc`. The block exports `JRNL_FILE`, adds `~/.local/bin` to PATH if needed, and sources the installed integration. Existing configuration outside the block is retained; before a change, the previous file is backed up to `.zshrc.jrnl.bak`. Repeating unchanged setup leaves the configuration and backup untouched.

`jrnl --setup` changes the journal path. The previous `bash jrnl.sh --setup` command also installs the files and migrates an existing managed block away from repo paths. If no path is configured, logging an entry prompts for one and then saves that entry.

## Use

In interactive zsh, start a line with `jrnl`; its ZLE integration treats the entry as literal text, including quotes, `$`, pipes and punctuation. No quoting is needed, and your command stays readable on screen and in history:

```text
jrnl Investigated strange network traffic today.
jrnl Why did <this> happen? {} # []., $foo | whatever
jrnl -- - [ ] Example task.
```

```md
## 2026-09-26

###### [23:43:01]

- [ ] Example task.
```

Entries are newest-first within each day, with new days above older days. Each new entry has a timestamp heading, a blank line, then the literal text, so Markdown tasks and lists work. Use `jrnl -- TEXT` when the entry starts with `-`. Entries must be a single line; older entries retain their existing format.

After a write, jrnl shows the timestamp and text, then the journal basename and directory on separate lines, followed by a hint to run `jrnl --show` or `jrnl -o`. Terminal output colors the checkmark green, the timestamp purple, the entry blue, and the complete hint yellow. Brackets and path lines stay uncolored. Piped/redirected output, an unset or `dumb` terminal, and a nonempty `NO_COLOR` disable color.

| Flag | Action |
| --- | --- |
| `--help`, `-h` | Show help |
| `--version`, `-V` | Show version |
| `--setup` | Install/configure jrnl and choose the journal path |
| `--check` | Show the current path |
| `--open`, `-o` | Open in the default app |
| `--show` | Print the journal to stdout |
| `-- TEXT` | Log text beginning with a flag, e.g. `jrnl -- --help` |

The executable also works directly in scripts or other shells: export `JRNL_FILE` and quote shell-sensitive text normally, for example `~/.local/bin/jrnl 'Why <this>?'`. Literal input capture applies only to standalone `jrnl` lines in interactive zsh. To rerun an entry, recall it into the prompt (for example, with Up-arrow); immediate history execution such as `!!` or `fc -s` uses normal shell parsing. Existing `jrnl` aliases or functions are kept with a warning; remove or rename a collision and reload the integration to enable it. Search with `grep -n 'network' "$JRNL_FILE"`.

Writes use a temporary file and atomic replacement. Locks record the owner's PID; a later command recovers a dead owner's lock automatically. Active locks fail with a busy message. Empty legacy locks, incomplete locks or reused live PIDs require manual inspection: stop any active jrnl processes before removing a leftover `<file>.lock` directory. A forced kill may also leave an unused `<file>.tmp.*` file. Journal and setup operations are local; jrnl does not send your entries anywhere.

## Uninstall

Remove only the lines from `# >>> jrnl >>>` through `# <<< jrnl <<<` in your `.zshrc`, then remove the installed files and start a new shell:

```sh
rm -- "$HOME/.local/bin/jrnl" "$HOME/.local/share/jrnl/jrnl.zsh"
```

Your journal and `.zshrc.jrnl.bak` remain in place.

## Development

```sh
python3 tests/test_jrnl.py
bash -n jrnl.sh
bash -n install.sh
zsh -n jrnl.zsh
shellcheck -x jrnl.sh install.sh
```

Tests use temporary homes and real terminal sessions to cover Markdown spacing, flags, color boundaries, clean ZLE display and history recall, installation, repo removal, atomic-write failures and stale-lock recovery. ShellCheck is a development dependency only. Linux compatibility work is deferred.
