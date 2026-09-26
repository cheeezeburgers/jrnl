# Development log

## 2026-09-26 — 0.1.1a

Branch: `codex/stable-install-locks`.

- Replaced repo-dependent setup with copied user-local executable and zsh integration; added a repeatable installer and non-mutating dry-run.
- Preserved managed-block position, backups and literal zsh input; unchanged setup no longer rewrites configuration or its backup.
- Added PID ownership and exclusive stale-lock recovery while retaining atomic writes. Unknown/legacy locks remain conservative manual-recovery cases; forced termination can leave unused temporary files.
- Expanded regression coverage for installed operation after checkout removal, flags, shell-sensitive text and paths, collisions, crash recovery, and competing recovery attempts.
- Validation on macOS: 23 integration tests passed, including real interactive zsh; Bash/zsh syntax checks, ShellCheck and whitespace checks passed.
- Version changed once, from `0.0.1a` to `0.1.1a`. Linux behavior was left unchanged; compatibility work remains deferred.
