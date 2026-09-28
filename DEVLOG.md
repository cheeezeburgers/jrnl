# Development log

## 2026-09-28 — 0.2.0a

Branch: `feat/setup-menus`.

- Replaced the single path prompt with clack-bash location and filename selectors, defaulting to `~/Documents/jrnl.md`. Custom inputs use Bash Readline completion; filename completion uses an existing chosen directory. Normalize `.md` case-insensitively and reject directory-valued filenames while retaining literal paths and existing resolution/configuration behavior.
- Vendored the minimal selector and helpers from clack-bash commit `afe36b88ab574b14a7bbc05ed1707fb4d9849ee5`, with attribution, MIT terms, and documented adaptations. Retained upstream selection controls/rendering; added an initial index, EOF handling, scoped signal/cleanup traps, and terminal-aware output. Verified on macOS Bash 3.2 without new runtime dependencies.
- Install the selector (including embedded MIT terms) as `~/.local/share/jrnl/clack-select.sh` alongside the unchanged zsh integration. Extended dry-run, source validation, atomic copying, reinstall and unrelated-file protection; updated setup and uninstall documentation.
- All 45 tests pass on macOS with Bash 3.2, including choices/defaults, suffix normalization, validation, symlinks, Readline Tab completion, Ctrl+C, repo removal, reinstall/dry-run and existing config/ZLE/locking coverage. Terminal tests now claim a controlling terminal to exercise signals. Aligned stale success-output expectations with existing main behavior; logging output was not changed.
- Bash/zsh syntax checks, ShellCheck and whitespace checks passed. Version bumped once from 0.1.2a to 0.2.0a. Both prior local work branches were already contained in main, so no merge was needed. No commits or pushes. ANSI terminals provide the interactive rendering; Linux validation remains deferred.

## 2026-09-27 — 0.1.2a

Branch: `codex/jrnl-display-format`.

- Put new timestamps in H6 headings with blank lines around literal entry text and between entries, enabling Markdown tasks while retaining newest-first insertion and existing journal text.
- Renamed `--cat` to `--show`; added the requested success message, separate basename/directory lines, and terminal-only ANSI colors with `NO_COLOR` support.
- Kept ZLE capture and escaping. `zle -I` finishes the original display before replacing the execution buffer; a scoped `zshaddhistory` hook uses `print -rs` and `fc -p` to retain readable history without the escaped duplicate. Existing hooks and non-jrnl commands continue working.
- Expanded coverage to 33 passing tests on macOS (Bash 3.2, zsh 5.9), including exact Markdown/output, real terminal color boundaries, clean display at different widths, readable history and recall, all flags, setup, installation/dry-run, atomic failures and lock recovery. Bash/zsh syntax, ShellCheck and whitespace checks passed.
- Corrected the session target version from `0.1.1a` to `0.1.2a`, including README and test expectations; no tests were rerun for this version-only correction. Linux integration remains deferred. Old entries are not reformatted; literal history replay requires recalling into ZLE, rather than immediate `!!`/`fc -s` execution.

## 2026-09-26 — 0.1.1a

Branch: `fix/stable-install-locks`.

- Replaced repo-dependent setup with copied user-local executable and zsh integration; added a repeatable installer and non-mutating dry-run.
- Preserved managed-block position, backups and literal zsh input; unchanged setup no longer rewrites configuration or its backup.
- Added PID ownership and exclusive stale-lock recovery while retaining atomic writes. Unknown/legacy locks remain conservative manual-recovery cases; forced termination can leave unused temporary files.
- Expanded regression coverage for installed operation after checkout removal, flags, shell-sensitive text and paths, collisions, crash recovery, and competing recovery attempts.
- Validation on macOS: 23 integration tests passed, including real interactive zsh; Bash/zsh syntax checks, ShellCheck and whitespace checks passed.
- Version changed once, from `0.0.1a` to `0.1.1a`. Linux behavior was left unchanged; compatibility work remains deferred.
