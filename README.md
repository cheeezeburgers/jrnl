# jrnl

A tiny Markdown engineering diary. Requires Bash and standard macOS/Linux tools; use interactive zsh for unquoted punctuation.

From this directory, set the journal path (folders and the `.md` file are created):

```sh
bash jrnl.sh --setup
source "${ZDOTDIR:-$HOME}/.zshrc"
jrnl Investigated strange network traffic today.
jrnl Why did <this> happen? {} # [].,
```

Setup adds a managed block to `.zshrc`, backing up an existing file to `.zshrc.jrnl.bak`. Keep this project folder in place. Run `jrnl --setup` to change the journal; if no path is configured, jrnl prompts for one and then saves your entry.

```md
## 2026-09-26

[13:26:21] Investigated strange network traffic today.
```

Newest entries appear first within each day; new days appear above older days. Each write prints the saved text and full file path.

| Flag | Action |
| --- | --- |
| `--help`, `-h` | Show help |
| `--version`, `-V` | Show version |
| `--setup` | Set the journal path |
| `--check` | Show the current path |
| `--open`, `-o` | Open in the default app (`xdg-open` on Linux) |
| `--cat` | Print the journal with `cat` |
| `-- TEXT` | Log text beginning with a flag |

In interactive zsh, start the line with `jrnl`: everything after it is literal, including quotes, `$`, pipes and punctuation. In other shells or scripts, use `bash /path/to/jrnl.sh 'Text with <punctuation>?'` with `JRNL_FILE` exported. Search with `grep -n 'network' "$JRNL_FILE"`.

Checks: `python3 tests/test_jrnl.py` (Python is only needed for tests).
