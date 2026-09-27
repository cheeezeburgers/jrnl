#!/usr/bin/env bash
# Small Markdown journal; compatible with the Bash shipped with macOS.
# jrnl: installed command
set -euo pipefail

VERSION=0.1.2a
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
SCRIPT_FILE=$SCRIPT_DIR/$(basename -- "${BASH_SOURCE[0]}")
INSTALLED_COMMAND=$HOME/.local/bin/jrnl
INSTALLED_INTEGRATION=$HOME/.local/share/jrnl/jrnl.zsh

error() { printf 'jrnl: %s\n' "$*" >&2; exit 1; }

help() {
    cat <<'HELP'
Usage: jrnl ENTRY...
       jrnl [OPTION]

Write a timestamped entry to a Markdown journal, newest first.

  -h, --help     Show this help
  -V, --version  Show the version
  --setup        Install jrnl, choose a journal and configure .zshrc
  --check        Show the configured journal path
  -o, --open     Open the journal in the default application
  --show         Print the journal contents
  --             Treat the following text as an entry, including flags

First run: ./install.sh, then ~/.local/bin/jrnl --setup and source your .zshrc.
Setup uses ~/.zshrc (or $ZDOTDIR/.zshrc) and stable files under ~/.local.
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
    if [[ -n "${lock_dir:-}" ]]; then
        rmdir -- "$lock_dir/$$" 2>/dev/null || :
        rmdir -- "$lock_dir" 2>/dev/null || :
    fi
    temp_file=
    lock_dir=
    return 0
}

lock_file() {
    local target=$1 candidate=$1.lock owner
    local -a owners
    temp_file=
    lock_dir=
    if ! mkdir -- "$candidate" 2>/dev/null; then
        # An empty PID directory is both the owner record and the recovery claim.
        # Only one recovering process can remove it; a loser must not remove
        # the outer lock, which might already belong to a new writer.
        owners=("$candidate"/[1-9]*)
        owner=${owners[0]##*/}
        [[ ! -L "$candidate" && ${#owners[@]} == 1 && "$owner" =~ ^[1-9][0-9]*$ &&
           -d "${owners[0]}" && ! -L "${owners[0]}" ]] ||
            error "Cannot acquire lock: $candidate (owner unknown). Check for active jrnl processes before removing this lock manually."
        if kill -0 "$owner" 2>/dev/null || ps -p "$owner" >/dev/null 2>&1; then
            error "File is busy: $target (lock owner PID $owner)"
        fi
        if ! rmdir -- "$candidate/$owner" 2>/dev/null ||
           ! rmdir -- "$candidate" 2>/dev/null ||
           ! mkdir -- "$candidate" 2>/dev/null; then
            error "Cannot acquire lock: $candidate; retry the command."
        fi
    fi
    lock_dir=$candidate
    trap cleanup EXIT
    trap 'exit 129' HUP
    trap 'exit 130' INT
    trap 'exit 143' TERM
    mkdir -- "$lock_dir/$$" || error "Cannot record lock owner: $lock_dir"
}

# Install actual copies, never symlinks into the checkout. Shared by --setup and
# install.sh so invoking setup directly still produces a complete installation.
install_copy() {
    local source=$1 destination=$2 mode=$3
    [[ ! "$source" -ef "$destination" ]] || return 0
    lock_file "$destination"
    temp_file=$(mktemp "$destination.tmp.XXXXXX") || error "Cannot create temporary installation: $destination"
    cp -- "$source" "$temp_file"
    chmod "$mode" "$temp_file"
    mv -f -- "$temp_file" "$destination"
    temp_file=
    cleanup
}

install_files() {
    local dry_run=${1:-0} integration=$SCRIPT_DIR/jrnl.zsh destination marker found dependency
    if [[ "$SCRIPT_FILE" -ef "$INSTALLED_COMMAND" ]]; then
        integration=$INSTALLED_INTEGRATION
    fi
    [[ -r "$SCRIPT_FILE" && -r "$integration" ]] || error 'Missing installation files; run ./install.sh from a complete checkout.'
    for dependency in bash zsh awk cat cp chmod cmp date dirname basename grep mkdir mktemp mv ps readlink rm rmdir uname; do
        command -v "$dependency" >/dev/null 2>&1 || error "Required command not found: $dependency"
    done
    # Refuse to replace an unrelated command, symlink, or directory.
    for destination in "$INSTALLED_COMMAND" "$INSTALLED_INTEGRATION"; do
        marker='# jrnl: installed command'
        [[ "$destination" != "$INSTALLED_INTEGRATION" ]] || marker='# Loaded by the managed jrnl block in .zshrc.'
        if [[ -e "$destination" || -L "$destination" ]]; then
            if [[ ! -f "$destination" || -L "$destination" ]] || ! grep -Fxq -- "$marker" "$destination"; then
                error "Refusing to replace unrelated file: $destination"
            fi
        fi
    done
    found=$(command -v jrnl || :)
    if [[ -n "$found" && "$found" != "$INSTALLED_COMMAND" ]]; then
        printf '[ ! ] Another jrnl command is on PATH: %s. Use %s explicitly.\n' "$found" "$INSTALLED_COMMAND" >&2
    fi
    if (( dry_run )); then
        printf '[DRY] Would install %s and %s\n[DRY] No changes made.\n' "$INSTALLED_COMMAND" "$INSTALLED_INTEGRATION"
        return
    fi
    mkdir -p -- "$(dirname -- "$INSTALLED_COMMAND")" "$(dirname -- "$INSTALLED_INTEGRATION")"
    install_copy "$integration" "$INSTALLED_INTEGRATION" 644
    install_copy "$SCRIPT_FILE" "$INSTALLED_COMMAND" 755
    printf '[ OK ] jrnl %s installed: %s\n' "$VERSION" "$INSTALLED_COMMAND"
    case ":$PATH:" in
        *:"$HOME/.local/bin":*) ;;
        *) printf '[ ! ] ~/.local/bin is not on PATH; --setup adds it to the managed zsh block.\n' ;;
    esac
}

save_config() {
    local rc=$1 block
    lock_file "$rc"
    temp_file=$(mktemp "$rc.jrnl.XXXXXX") || error "Cannot create temporary configuration"
    block=$(
        printf '# >>> jrnl >>>\n'
        printf 'export JRNL_FILE=%q\n' "$JRNL_FILE"
        # shellcheck disable=SC2016 # Expanded when zsh reads its configuration.
        printf '%s\n' 'case ":$PATH:" in
    *:"$HOME/.local/bin":*) ;;
    *) export PATH="$HOME/.local/bin:$PATH" ;;
esac'
        printf 'source %q\n' "$INSTALLED_INTEGRATION"
        printf '# <<< jrnl <<<\n'
    )
    if [[ -e "$rc" ]]; then
        [[ -f "$rc" && -r "$rc" && -w "$rc" ]] || error "Cannot update $rc"
        cp -p -- "$rc" "$temp_file"
        # Replace the block in place, preserving configuration on either side.
        # Refuse malformed markers rather than dropping unrelated configuration.
        JRNL_BLOCK="$block" awk '
            $0 == "# >>> jrnl >>>" {
                if (inside) exit 2
                inside = 1
                if (!seen++) print ENVIRON["JRNL_BLOCK"]
                next
            }
            $0 == "# <<< jrnl <<<" { if (!inside) exit 2; inside = 0; next }
            !inside { print }
            END {
                if (inside) exit 2
                if (!seen) { if (NR) print ""; print ENVIRON["JRNL_BLOCK"] }
            }
        ' "$rc" > "$temp_file" || error "Malformed jrnl block in $rc"
        if cmp -s -- "$rc" "$temp_file"; then
            cleanup
            return
        fi
        [[ ! -L "$rc.jrnl.bak" && ( ! -e "$rc.jrnl.bak" || -f "$rc.jrnl.bak" ) ]] ||
            error "Cannot safely write backup: $rc.jrnl.bak"
        cp -p -- "$rc" "$rc.jrnl.bak"
    else
        printf '%s\n' "$block" > "$temp_file"
    fi
    mv -f -- "$temp_file" "$rc"
    temp_file=
    cleanup
}

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
    rc=$(resolve_path "${ZDOTDIR:-$HOME}/.zshrc")
    [[ "$rc" != "$JRNL_FILE" ]] || error 'The journal and shell configuration must be different files.'
    install_files
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

write_success() {
    local time=$1 entry=$2 green='' purple='' blue='' yellow='' reset=''
    if [[ -t 1 && -n ${TERM:-} && ${TERM:-} != dumb && -z ${NO_COLOR:-} ]]; then
        green=$'\033[32m'
        purple=$'\033[35m'
        blue=$'\033[34m'
        yellow=$'\033[33m'
        reset=$'\033[0m'
    fi
 	printf '\n[%s✓%s] [%s%s%s] %s%s%s\n' \
    	"$green" "$reset" "$purple" "$time" "$reset" "$blue" "$entry" "$reset"
	printf '    was written to %s\n    in %s/\n' "${JRNL_FILE##*/}" "${JRNL_FILE%/*}"
	printf '%s[i] Show all entries with jrnl --show or open with jrnl -o%s\n' "$yellow" "$reset"
}

write_entry() {
    local entry=$1 stamp day time
    ensure_file
    lock_file "$JRNL_FILE"
    stamp=$(date '+%Y-%m-%d %H:%M:%S')
    day=${stamp% *}
    time=${stamp#* }
    temp_file=$(mktemp "$JRNL_FILE.tmp.XXXXXX") || error 'Cannot create temporary journal.'
    cp -p -- "$JRNL_FILE" "$temp_file"
    # ENVIRON keeps backslashes literal; awk -v would interpret escapes.
    JRNL_HEADING="## $day" JRNL_ENTRY="###### [$time]"$'\n\n'"$entry" awk '
        BEGIN { heading = ENVIRON["JRNL_HEADING"]; entry = ENVIRON["JRNL_ENTRY"] }
        { lines[NR] = $0; if ($0 == heading) found = 1 }
        END {
            if (!found) {
                print heading; print ""; print entry; print ""
            }
            for (i = 1; i <= NR; i++) {
                print lines[i]
                if (lines[i] == heading && !inserted) {
                    print ""; print entry; print ""; inserted = 1
                    while (i < NR && lines[i + 1] == "") i++
                }
            }
        }
    ' "$JRNL_FILE" > "$temp_file"
    mv -f -- "$temp_file" "$JRNL_FILE"
    temp_file=
    cleanup
    write_success "$time" "$entry"
}

main() {
    local action=entry entry
    if (( $# == 0 )); then help; return; fi
    case "$1" in
        --) shift ;;
        -h|--help|-V|--version|--setup|--check|-o|--open|--show)
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
        --show)
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

# install.sh sources the same version and installation helpers.
if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
    main "$@"
fi
