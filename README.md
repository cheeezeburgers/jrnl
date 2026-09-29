# jrnl

__A tiny engineering diary for your terminal.__

![jrnl-hero-img](assets/jrnl-hero-img.png)

Write down what you just fixed, broke, investigated or want to remember, without leaving the terminal.

![jrnl-demo](assets/jrnl-demo.gif)

`jrnl` saves it to a Markdown file with the current date and time.

> [!NOTE]
> __Version 0.2.3__ — Tested on macOS with Bash 3.2 and zsh. Linux validation is planned for a later version.

## Install

### Dry-run

> [!TIP]
> You can preview the installation without installing anything:
> ```sh
> ./install.sh --dry-run
> ```

### Installation

Clone the repo, then run:

```sh
./install.sh
~/.local/bin/jrnl --setup
source "${ZDOTDIR:-$HOME}/.zshrc"
```

> [!NOTE]
> If you use `make`, installation can also be started with:
> 
> ```sh
> make install
> ```
> 
> This is only a convenience wrapper around `./install.sh`.

The installer copies everything `jrnl` needs to stable user-local locations:

```text
~/.local/bin/jrnl
~/.local/share/jrnl/jrnl.zsh
~/.local/share/jrnl/clack-select.sh
```

The setup selector is vendored with `jrnl`, so there is no separate UI dependency to install.

### Update

To update later, run `./install.sh` (or `make install`) again from a newer checkout.

## Setup

`jrnl --setup` first asks where your journal should live:

```text
Home
Documents
Other
```

**Documents** is the default.

It then asks for the journal filename:

```text
journal.md
jrnl.md
devlog.md
Other
```

**jrnl.md** is the default.

> [!TIP]
> Accepting both defaults creates `~/Documents/jrnl.md`.

Choosing **Other** lets you enter your own directory or filename. These prompts support normal Tab completion.

If you enter a custom filename without a suffix, `jrnl` adds `.md` automatically. Existing suffixes are kept:

```text
dev-journal       → dev-journal.md
dev-journal.md    → dev-journal.md
notes.txt         → notes.txt
```

Run `jrnl --setup` again whenever you want to move to a different journal.

## Use

Just write:

```sh
jrnl Investigated strange network traffic today.
```

No quotes needed.

Even shell-looking text stays journal text:

```sh
jrnl Why did <this> happen? {} # []., $foo | whatever
```

> [!TIP]
> Want to journal the command you just ran? zsh expands `!!` to the previous command:
>
> ```
> ❯ git status
> On branch main [...]
> 
> ❯ jrnl I used !! command
> ```
> 
> Creates directly after space:
>
> ```
> ❯ jrnl I used git status command
> ```

In interactive zsh, `jrnl` uses a small ZLE integration to capture everything after the command literally before the shell gets creative with it.

Your command still looks normal in the terminal and shell history.

The journal looks like this:

```md
## 2026-09-26

###### [23:43:01]

Investigated strange network traffic today.

###### [23:42:00]

- [ ] Fix this tomorrow.
```

Newest entries come first within each day. New days are added above older ones.

Because the entry itself is regular Markdown, tasks and lists work too:

```sh
jrnl -- - [ ] Fix this tomorrow.
```

The `--` tells `jrnl` that what follows is an entry, even when it starts with `-`.

After writing, you get a small confirmation:

```text
[✓] [00:49:08] This is a test for next day.
    was written to dev-journal.md
    in /Users/example/vscode-projects/
[i] Show all entries with jrnl --show or open with jrnl -o
```

## Commands

| Command | What it does |
| --- | --- |
| `jrnl TEXT` | Write a new entry |
| `jrnl -- TEXT` | Write an entry beginning with `-` or another flag-like value |
| `jrnl --show` | Print the complete journal |
| `jrnl --open`, `jrnl -o` | Open the journal in its default app |
| `jrnl --check` | Show the configured journal path |
| `jrnl --setup` | Choose or change the journal location and filename |
| `jrnl --version`, `jrnl -V` | Show the version |
| `jrnl --help`, `jrnl -h` | Show help |

Search the journal with whatever tools you already use:

```sh
grep -n 'network' "$JRNL_FILE"
```

## Configuration

`jrnl --setup` adds a small managed block to:

```text
~/.zshrc
```

or `$ZDOTDIR/.zshrc` when `ZDOTDIR` is set.

It stores the journal path, adds `~/.local/bin` to `PATH` when needed and loads the zsh integration.

The managed section looks like this:

```text
# >>> jrnl >>>
...
# <<< jrnl <<<
```

Everything outside that block is left alone.

Before changing an existing `.zshrc`, `jrnl` creates:

```text
.zshrc.jrnl.bak
```

Running setup again with unchanged configuration does not rewrite the file or create a new backup.

## Other shells

The executable itself is Bash and can also be called directly from scripts or other shells.

Set `JRNL_FILE` and quote shell-sensitive text normally:

```sh
export JRNL_FILE="$HOME/dev-journal.md"

jrnl 'Why did <this> happen?'
```

The quote-free literal input behavior is provided by the interactive zsh integration.

## Local by design

Your journal is just a Markdown file.

`jrnl` does not send entries anywhere, require an account or download anything while running.

The interactive setup menu is bundled with `jrnl` as a small Bash selector adapted from [clack-bash](https://github.com/ibrahimhajjaj/clack-bash), licensed under MIT. No additional runtime dependency is required.

Writes use a temporary file followed by atomic replacement to avoid leaving a half-written journal behind.

A small PID-based lock prevents two processes from writing the same file at once and can recover locks left behind by dead processes.

## Uninstall

Remove the managed `jrnl` block from `.zshrc`:

```text
# >>> jrnl >>>
...
# <<< jrnl <<<
```

Then remove the installed files:

```sh
rm -- "$HOME/.local/bin/jrnl"
rm -- "$HOME/.local/share/jrnl/jrnl.zsh"
rm -- "$HOME/.local/share/jrnl/clack-select.sh"
```

Your journal and `.zshrc.jrnl.bak` are left untouched.

## Release

For maintainers, the Makefile keeps tagging and releases short:

```sh
make tag
make release
```

`make tag` creates an annotated local tag from the current project version.

`make release` verifies that tag, pushes only that version tag to `origin`, then creates the matching GitHub release with generated notes using `gh`.

## Development

Run the tests:

```sh
python3 development/tests/test_jrnl.py
```

Syntax checks:

```sh
bash -n jrnl.sh
bash -n install.sh
zsh -n jrnl.zsh
```

Lint:

```sh
shellcheck -x jrnl.sh install.sh
```

Python and ShellCheck are development dependencies only.

Linux compatibility and validation are planned for a later version.