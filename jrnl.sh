#!/usr/bin/env bash
# Small Markdown journal; compatible with the Bash shipped with macOS.
set -euo pipefail

VERSION=1.0.0
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)

error() { printf 'jrnl: %s\n' "$*" >&2; exit 1; }

help() {
    cat <<'HELP'
Usage: jrnl ENTRY...
       jrnl [OPTION]

Write a timestamped entry to a Markdown journal, newest first.

  -h, --help     Show this help
  -V, --version  Show the version
  --setup        Choose a journal and configure ~/.zshrc (or $ZDOTDIR/.zshrc)
  --check        Show the configured journal path
  -o, --open     Open the journal in the default application
  --cat          Print the journal using cat
  --             Treat the following text as an entry, including flags

First run: bash jrnl.sh --setup, then source your .zshrc.
With the zsh integration, type jrnl followed by literal text without quotes.
In other shells or scripts, quote shell punctuation: jrnl 'Why <this>?'
HELP
}

# Resolve paths without eval, including existing symlinks, before atomic writes.
resolve_path() {
    local target=$1 link count=0
    case "$target" in
        \~) target=$HOME ;;
        \~/*) target=$HOME/${target#\~/} ;;
    esac
    [[ "$target" == /* ]] || target=$PWD/$target
    while [[ -L "$target" ]]; do
        count=$((count + 1))
        (( count <= 40 )) || error "Too many symlinks: $target"
        link=$(readlink "$target") || error "Cannot resolve $target"
        case "$link" in
            /*) target=$link ;;
            *) target=$(dirname -- "$target")/$link ;;
        esac
    done
    printf '%s\n' "$target"
}

ensure_file() {
    local parent
    parent=$(dirname -- "$JRNL_FILE")
    mkdir -p -- "$parent" || error "Cannot create directory: $parent"
    JRNL_FILE=$(cd -- "$parent" && printf '%s/%s' "$(pwd -P)" "$(basename -- "$JRNL_FILE")")
    [[ ! -e "$JRNL_FILE" || -f "$JRNL_FILE" ]] || error "Not a regular file: $JRNL_FILE"
    (umask 077; : >> "$JRNL_FILE") || error "Cannot write journal: $JRNL_FILE"
    [[ -r "$JRNL_FILE" && -w "$JRNL_FILE" ]] || error "Journal must be readable and writable: $JRNL_FILE"
    export JRNL_FILE
}

# Each write owns a lock and a temporary file in the destination directory.
# An interrupted write leaves the original file intact.
cleanup() {
    [[ -z "${temp_file:-}" ]] || rm -f -- "$temp_file"
    [[ -z "${lock_dir:-}" ]] || rmdir -- "$lock_dir"
    return 0
}

lock_file() {
    local target=$1
    temp_file=
    lock_dir=
    mkdir -- "$target.lock" 2>/dev/null || error "File is busy or its directory is not writable: $target (lock: $target.lock)"
    lock_dir=$target.lock
    trap cleanup EXIT
    trap 'exit 129' HUP
    trap 'exit 130' INT
    trap 'exit 143' TERM
}

save_config() (
    local rc=$1
    lock_file "$rc"
    temp_file=$(mktemp "$rc.jrnl.XXXXXX") || error "Cannot create temporary configuration"
    if [[ -e "$rc" ]]; then
        [[ -f "$rc" && -r "$rc" && -w "$rc" ]] || error "Cannot update $rc"
        cp -p -- "$rc" "$temp_file"
        # Refuse malformed markers rather than dropping unrelated configuration.
        awk '
            $0 == "# >>> jrnl >>>" { if (inside) exit 2; inside = 1; next }
            $0 == "# <<< jrnl <<<" { if (!inside) exit 2; inside = 0; next }
            !inside { print }
            END { if (inside) exit 2 }
        ' "$rc" > "$temp_file" || error "Malformed jrnl block in $rc"
        cp -p -- "$rc" "$rc.jrnl.bak"
    fi
    {
        printf '\n# >>> jrnl >>>\n'
        printf 'export JRNL_FILE=%q\n' "$JRNL_FILE"
        printf 'source %q\n' "$SCRIPT_DIR/jrnl.zsh"
        printf '# <<< jrnl <<<\n'
    } >> "$temp_file"
    mv -f -- "$temp_file" "$rc"
    temp_file=
)

setup() {
    local chosen default rc
    default=${JRNL_FILE:-$HOME/journal.md}
    printf 'Journal file path [%s]: ' "$default" >&2
    IFS= read -r chosen || error 'Setup cancelled: no path received.'
    chosen=${chosen:-$default}
    [[ "$chosen" != *$'\n'* && "$chosen" != *$'\r'* ]] || error 'The path must be a single line.'
    [[ "$chosen" != */ && ! -d "$chosen" ]] || error 'Please include a Markdown filename, for example ~/notes/journal.md.'
    case "$chosen" in *.md|*.MD) ;; *) chosen=$chosen.md ;; esac
    JRNL_FILE=$(resolve_path "$chosen")
    ensure_file
    [[ -r "$SCRIPT_DIR/jrnl.zsh" ]] || error "Missing zsh integration: $SCRIPT_DIR/jrnl.zsh"
    rc=$(resolve_path "${ZDOTDIR:-$HOME}/.zshrc")
    [[ "$rc" != "$JRNL_FILE" ]] || error 'The journal and shell configuration must be different files.'
    mkdir -p -- "$(dirname -- "$rc")"
    save_config "$rc"
    printf 'Journal: %s\nConfiguration: %s\n' "$JRNL_FILE" "$rc"
    printf 'To load jrnl in a new shell, run: source %q\n' "${ZDOTDIR:-$HOME}/.zshrc"
}

require_config() {
    if [[ -z "${JRNL_FILE:-}" ]]; then
        printf 'jrnl: No journal path is configured (JRNL_FILE).\n' >&2
        setup
    else
        JRNL_FILE=$(resolve_path "$JRNL_FILE")
    fi
}

write_entry() (
    local entry=$1 stamp day time
    ensure_file
    lock_file "$JRNL_FILE"
    stamp=$(date '+%Y-%m-%d %H:%M:%S')
    day=${stamp% *}
    time=${stamp#* }
    entry="[$time] $entry"
    temp_file=$(mktemp "$JRNL_FILE.tmp.XXXXXX") || error 'Cannot create temporary journal.'
    cp -p -- "$JRNL_FILE" "$temp_file"
    # ENVIRON keeps backslashes literal; awk -v would interpret escapes.
    JRNL_HEADING="## $day" JRNL_ENTRY="$entry" awk '
        BEGIN { heading = ENVIRON["JRNL_HEADING"]; entry = ENVIRON["JRNL_ENTRY"] }
        { lines[NR] = $0; if ($0 == heading) found = 1 }
        END {
            if (!found) {
                print heading; print ""; print entry; print ""
            }
            for (i = 1; i <= NR; i++) {
                print lines[i]
                if (lines[i] == heading && !inserted) {
                    print ""; print entry; inserted = 1
                    while (i < NR && lines[i + 1] == "") i++
                    # Keep a blank line between days when an empty section exists.
                    if (i < NR && lines[i + 1] ~ /^## /) print ""
                }
            }
        }
    ' "$JRNL_FILE" > "$temp_file"
    mv -f -- "$temp_file" "$JRNL_FILE"
    temp_file=
    printf 'Written to %s:\n%s\n' "$JRNL_FILE" "$entry"
)

main() {
    local action=entry entry
    if (( $# == 0 )); then help; return; fi
    case "$1" in
        --) shift ;;
        -h|--help|-V|--version|--setup|--check|-o|--open|--cat)
            (( $# == 1 )) || error 'Options must be used alone. Use jrnl -- TEXT to log text starting with a flag.'
            action=$1 ;;
        -*) error "Unknown option: $1 (see jrnl --help; use -- to log a leading dash)." ;;
    esac
    case "$action" in
        -h|--help) help; return ;;
        -V|--version) printf 'jrnl %s\n' "$VERSION"; return ;;
        --setup) setup; return ;;
        entry)
            entry=$*
            [[ "$entry" == *[![:space:]]* ]] || error 'Entry cannot be empty.'
            [[ "$entry" != *$'\n'* && "$entry" != *$'\r'* ]] || error 'Entries must be a single line.' ;;
    esac
    require_config
    case "$action" in
        --check) printf 'Journal: %s\n' "$JRNL_FILE" ;;
        --cat)
            [[ -f "$JRNL_FILE" ]] || error "Journal does not exist: $JRNL_FILE"
            cat -- "$JRNL_FILE" ;;
        -o|--open)
            [[ -f "$JRNL_FILE" ]] || error "Journal does not exist: $JRNL_FILE"
            case "$(uname -s)" in
                Darwin) open "$JRNL_FILE" ;;
                Linux)
                    command -v xdg-open >/dev/null 2>&1 || error 'xdg-open is required to open the journal on Linux.'
                    xdg-open "$JRNL_FILE" ;;
                *) error 'Opening the journal is supported on macOS and Linux.' ;;
            esac ;;
        entry) write_entry "$entry" ;;
    esac
}

main "$@"
