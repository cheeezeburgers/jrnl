# Development log

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
