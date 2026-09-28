# jrnl

__A tiny engineering diary for your terminal.__

![jrnl-hero-img](assets/jrnl-hero-img.png)

Write down what you just fixed, broke, investigated or want to remember, without leaving the terminal.

![jrnl-demo](assets/jrnl-demo.gif)

"jrnl" saves it to a Markdown file with the current date and time.

> [!NOTE]
> __Version 0.1.2a__ -- Tested on macOS with Bash 3.2 and zsh.

## Install

Clone the repo, then run:

```sh
./install.sh
jrnl --setup
source "${ZDOTDIR:-$HOME}/.zshrc"
```

`jrnl --setup` asks where your journal should live and creates the file and missing folders for you.

The installer puts:

```text
~/.local/bin/jrnl
~/.local/share/jrnl/jrnl.zsh
```

in stable user-local locations, so the cloned repo can be moved or deleted afterwards.

To preview the install without changing anything:

```sh
./install.sh --dry-run
```

To update later, run `./install.sh` again from a newer checkout.

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

The checkmark is green, the timestamp orange, the repeated entry blue and the information line yellow.

Colors are automatically disabled when output is redirected or piped, when the terminal does not support them, or when `NO_COLOR` is set.

## Commands

| Command | What it does |
| --- | --- |
| `jrnl TEXT` | Write a new entry |
| `jrnl -- TEXT` | Write an entry beginning with `-` or another flag-like value |
| `jrnl --show` | Print the complete journal |
| `jrnl --open`, `jrnl -o` | Open the journal in its default app |
| `jrnl --check` | Show the configured journal path |
| `jrnl --setup` | Choose or change the journal path |
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
```

Your journal and `.zshrc.jrnl.bak` are left untouched.

## Development

Run the tests:

```sh
python3 tests/test_jrnl.py
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

Linux compatibility is planned for a later version.