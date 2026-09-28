#!/usr/bin/env bash
# jrnl: installed clack-bash selector
# Derived from ibrahimhajjaj/clack-bash, commit
# afe36b88ab574b14a7bbc05ed1707fb4d9849ee5 (CLACK_VERSION=1.2.0).
# An implementation of @clack/prompts for Bash scripts.
# https://github.com/bombshell-dev/clack
# License: MIT. Copyright (c) 2026 Ibrahim Hajjaj.
# Full MIT terms follow; provenance and adaptations are in vendor/clack-bash/README.md.
# jrnl adaptations: plain choices only, initial index, scoped traps,
# stdin/EOF handling, terminal-aware output and NO_COLOR. Bash 3.2.

# MIT License
#
# Copyright (c) 2026 Ibrahim Hajjaj
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

__clack_cursor_hide() { if [[ -t 2 && ${TERM:-dumb} != dumb ]]; then printf '\033[?25l' >&2; fi; }
__clack_cursor_show() { if [[ -t 2 && ${TERM:-dumb} != dumb ]]; then printf '\033[?25h' >&2; fi; }
__clack_cursor_up() { printf '\033[%dA' "${1:-1}" >&2; }
__clack_cursor_to_col() { printf '\033[%dG' "${1:-0}" >&2; }
__clack_erase_line() { printf '\033[2K' >&2; }
__clack_print() { printf '%s\n' "$1" >&2; }

__clack_clear_lines() {
    [[ -t 2 && ${TERM:-dumb} != dumb ]] || return 0
    local n=${1:-1}
    local i
    for ((i = 0; i < n; i++)); do
        __clack_cursor_up 1
        __clack_erase_line
    done
    __clack_cursor_to_col 0
}

__clack_read_key() {
    local key
    CLACK_KEY=""

    # Read first character
    IFS= read -rsn1 key 2>/dev/null || return 1

    # Handle escape sequence
    if [[ "$key" == $'\x1b' ]]; then
        local seq=""

        # Try to read up to 3 more characters with timeout
        # Using longer timeout for macOS bash 3.2 compatibility
        if read -rsn1 -t 1 seq 2>/dev/null; then
            if [[ "$seq" == "[" ]]; then
                # CSI sequence: ESC [ ...
                local code=""
                if read -rsn1 -t 1 code 2>/dev/null; then
                    case "$code" in
                        A) CLACK_KEY="UP"; return ;;
                        B) CLACK_KEY="DOWN"; return ;;
                        C) CLACK_KEY="RIGHT"; return ;;
                        D) CLACK_KEY="LEFT"; return ;;
                        H) CLACK_KEY="HOME"; return ;;
                        F) CLACK_KEY="END"; return ;;
                        [0-9])
                            # Extended sequence like ESC [ 1 ~ or ESC [ 1 5 ~
                            local extra=""
                            read -rsn1 -t 1 extra 2>/dev/null || :
                            case "${code}${extra}" in
                                "1~"|"7~") CLACK_KEY="HOME"; return ;;
                                "4~"|"8~") CLACK_KEY="END"; return ;;
                                "3~") CLACK_KEY="DELETE"; return ;;
                                "5~") CLACK_KEY="PAGEUP"; return ;;
                                "6~") CLACK_KEY="PAGEDOWN"; return ;;
                            esac
                            ;;
                    esac
                fi
            elif [[ "$seq" == "O" ]]; then
                # SS3 sequence: ESC O ...
                local code=""
                if read -rsn1 -t 1 code 2>/dev/null; then
                    case "$code" in
                        A) CLACK_KEY="UP"; return ;;
                        B) CLACK_KEY="DOWN"; return ;;
                        C) CLACK_KEY="RIGHT"; return ;;
                        D) CLACK_KEY="LEFT"; return ;;
                        H) CLACK_KEY="HOME"; return ;;
                        F) CLACK_KEY="END"; return ;;
                    esac
                fi
            fi
        fi

        CLACK_KEY="ESCAPE"
        return
    fi

    # Handle special characters
    if [[ "$key" == "" ]]; then
        CLACK_KEY="ENTER"
    elif [[ "$key" == " " ]]; then
        CLACK_KEY="SPACE"
    elif [[ "$key" == $'\t' ]]; then
        CLACK_KEY="TAB"
    elif [[ "$key" == $'\x7f' ]] || [[ "$key" == $'\b' ]]; then
        CLACK_KEY="BACKSPACE"
    elif [[ "$key" == $'\x03' ]]; then
        # Ctrl+C
        CLACK_KEY="CTRL_C"
    else
        CLACK_KEY="$key"
    fi
}

clack_select() (
    local message="${1:-Select an option}"
    local cursor=$2
    shift 2
    local -a options=("$@")
    local count=${#options[@]}
    local C_RESET='' C_DIM='' C_RED='' C_GREEN='' C_CYAN='' C_GRAY=''
    local S_STEP_ACTIVE='*' S_STEP_SUBMIT='o' S_BAR='|' S_BAR_END='-'
    local S_RADIO_ACTIVE='>' S_RADIO_INACTIVE=' '
    case "${LC_ALL:-${LC_CTYPE:-${LANG:-}}}" in
        *UTF-8*|*utf8*)
            S_STEP_ACTIVE='◆'; S_STEP_SUBMIT='◇'; S_BAR='│'; S_BAR_END='└'
            S_RADIO_ACTIVE='❯'; S_RADIO_INACTIVE='' ;;
    esac
    if [[ -t 2 && ${TERM:-dumb} != dumb && -z ${NO_COLOR:-} ]]; then
        C_RESET=$'\033[0m'; C_DIM=$'\033[2m'; C_RED=$'\033[31m'
        C_GREEN=$'\033[32m'; C_CYAN=$'\033[36m'; C_GRAY=$'\033[90m'
    fi

    if ((count == 0 || cursor < 0 || cursor >= count)); then
        __clack_print "${C_RED}Error: No options provided${C_RESET}"
        return 1
    fi

    # A subshell keeps these traps separate from jrnl's file-lock cleanup.
    trap '__clack_cursor_show' EXIT
    trap 'exit 130' INT
    trap 'exit 129' HUP
    trap 'exit 143' TERM
    __clack_cursor_hide

    local total_lines=$((2 + count + 1))

    while true; do
        __clack_print "${C_GRAY}${S_BAR}${C_RESET}"
        __clack_print "${C_CYAN}${S_STEP_ACTIVE}${C_RESET}  ${message}"

        local i
        for ((i = 0; i < count; i++)); do
            local label="${options[$i]}"
            if ((i == cursor)); then
                __clack_print "${C_CYAN}${S_BAR}${C_RESET}  ${C_GREEN}${S_RADIO_ACTIVE} ${label}${C_RESET}"
            else
                __clack_print "${C_CYAN}${S_BAR}${C_RESET}  ${C_DIM}${S_RADIO_INACTIVE} ${C_DIM}${label}${C_RESET}"
            fi
        done

        __clack_print "${C_CYAN}${S_BAR_END}${C_RESET}"

        __clack_read_key || return 1

        case "$CLACK_KEY" in
            CTRL_C) return 130 ;;
            UP|k|K)
                cursor=$(((cursor + count - 1) % count))
                ;;
            DOWN|j|J)
                cursor=$(((cursor + 1) % count))
                ;;
            ENTER)
                break
                ;;
        esac

        __clack_clear_lines $total_lines
    done

    __clack_clear_lines $total_lines
    __clack_print "${C_GRAY}${S_BAR}${C_RESET}"
    __clack_print "${C_GREEN}${S_STEP_SUBMIT}${C_RESET}  ${message}"
    __clack_print "${C_GRAY}${S_BAR}${C_RESET}  ${C_DIM}${options[$cursor]}${C_RESET}"

    printf '%s' "${options[$cursor]}"
)
