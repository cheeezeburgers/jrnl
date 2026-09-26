#!/usr/bin/env bash
set -euo pipefail

INSTALLER_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
if [[ ! -r "$INSTALLER_DIR/jrnl.sh" || ! -r "$INSTALLER_DIR/jrnl.zsh" ]]; then
    printf 'jrnl: Missing installation files; use a complete checkout.\n' >&2
    exit 1
fi
# shellcheck source=jrnl.sh
source "$INSTALLER_DIR/jrnl.sh"

dry_run=0
case "${1:-}" in
    '') ;;
    --dry-run) dry_run=1 ;;
    -h|--help)
        printf 'Usage: ./install.sh [--dry-run]\nInstall jrnl into ~/.local/bin and its zsh integration into ~/.local/share/jrnl.\n'
        exit 0 ;;
    *) error 'Usage: ./install.sh [--dry-run]' ;;
esac
(( $# <= 1 )) || error 'Usage: ./install.sh [--dry-run]'
printf '[ .. ] Platform: %s (installation tested on macOS).\n' "$(uname -s)"
install_files "$dry_run"
if (( ! dry_run )); then
    printf 'Next: %q --setup\n' "$INSTALLED_COMMAND"
    case "${SHELL:-}" in
        zsh|*/zsh) ;;
        *) printf '[ .. ] Literal unquoted input requires interactive zsh; otherwise use quoted CLI arguments.\n' ;;
    esac
fi
