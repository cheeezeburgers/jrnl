# Development log

## 2026-09-30 — 0.2.4

Branch: `feature/push-tag`.

- Add `make push-tag` as a thin call to `development/release.sh`. Reuse the canonical version, clean-tree checks, annotated local tag at HEAD and sole origin push destination. This operation needs Git only and never invokes GitHub CLI.
- Share remote tag verification and publication with `make release`: compare both the annotated tag object and peeled commit, skip an already matching remote tag, reject conflicts or read failures, and push only the explicit version tag with follow-tags and mirroring disabled. Release retains its GitHub preflight and creates the release after either publishing or reusing the tag.
- Validate 18 release integration tests with disposable local Git repositories and mocked GitHub CLI, plus five existing version/installer regressions. Cover missing `gh`, overridden push destinations/settings, idempotent publication, release after push-tag, conflicts and transport failures. Bash syntax, ShellCheck, Make dry-run and whitespace checks pass on macOS; live GitHub publication and Linux execution were not tested.
- Bump the canonical version once from 0.2.3 to 0.2.4. No project tags, commits or pushes were made.

## 2026-09-29 — 0.2.3a

Branch: `feature/make-release`.

- Add a thin root Makefile: `make install` delegates to the canonical `./install.sh`; `make tag` and `make release` call a shared Bash maintainer helper. Commit changes before tagging; release requires the current annotated tag at HEAD.
- Read the canonical version via `jrnl.sh --version`; refuse dirty trees, unfinished Git operations, duplicate local tags, conflicting remote tags and existing GitHub releases (including drafts). Validate GitHub CLI, authentication, repository access and write permission before pushing only the explicit version tag to origin's sole push URL. Create releases with a versioned title and generated notes; failed publication leaves the pushed tag available for inspection/retry.
- Validate with `python3 development/tests/test_release.py` (16 passing tests using disposable repositories, real local Git transport and a mocked GitHub CLI), plus five existing installer/version regressions. Bash syntax, ShellCheck (`-x`), Make dry-run and whitespace checks pass on macOS Bash 3.2. Cover single-tag pushes with follow-tags enabled, matching/conflicting remote tags, existing releases, missing prerequisites, authentication/API/transport failures and retained tags after publication failure. Live GitHub publication and Linux execution were not tested.
- Version bumped once from 0.2.2a to 0.2.3a. Preserve README and standalone installation instructions as required. No project tags, commits or pushes were made.

## 2026-09-29 — 0.2.2a

Branch: `codex/fix-setup-retries`.

- Retry location and filename validation independently, retaining the selected location after filename errors. Preserve useful errors and cancellation on EOF/Ctrl+C; propagate signal failures instead of retrying them. Selector rendering and ZLE integration are unchanged.
- Trim surrounding filename whitespace while preserving internal spaces. Append `.md` only when there is no suffix; preserve existing suffixes and their casing, including `.txt`, and check directory targets after cleanup.
- Keep the relocated suite in `development/tests/`, fix its repository root and README test command, and use the canonical script version in tests. Align stale expectations with the existing UI. Preserve the relocated development log with a narrow ignore exception; README changes are limited to the explicitly requested test command.
- Add regression coverage for empty/invalid inputs, directory and symlink targets, whitespace/suffix handling, successful recovery at each selector, and real-terminal cancellation after retries. Final `python3 development/tests/test_jrnl.py`: 49 of 50 tests passed on macOS Bash 3.2/zsh 5.9, including all new regressions and installer/dry-run checks. Bash/zsh syntax, ShellCheck, executable permissions and whitespace checks passed.
- Remaining validation issue: the existing `test_real_terminal_defaults_and_cancellation` intermittently misses the selector's cursor-show escape after Ctrl+C. Reproduced against an isolated copy of the original `HEAD` implementation (7 failures in 16 diagnostic runs). Retained its assertion and left the selector unchanged; cancellation returns to the shell. Terminal synchronization experiments were removed.
- Version bumped once from 0.2.1a to 0.2.2a. No staging, commits, or pushes. Linux validation remains deferred.

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
