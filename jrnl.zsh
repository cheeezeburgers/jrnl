# Loaded by the managed jrnl block in .zshrc.
# The legacy wrapper called bash with JRNL_SCRIPT; allow it to migrate when an
# existing shell reloads .zshrc after installation.
if (( ${+aliases[jrnl]} )) || {
    (( ${+functions[jrnl]} )) &&
    [[ ${functions[jrnl]} != ${_JRNL_WRAPPER:-} &&
       ${functions[jrnl]} != *'command bash "$JRNL_SCRIPT" "$@"'* ]]
}; then
    print -u2 -- 'jrnl: An existing alias or function named jrnl was kept. Remove or rename it, then source this file again to enable literal input.'
    return 0
fi
typeset -g JRNL_SCRIPT="$HOME/.local/bin/jrnl"

jrnl() {
    local result line inside=0 refresh=0
    [[ -z ${JRNL_FILE:-} || ${1:-} == --setup ]] && refresh=1
    command "$JRNL_SCRIPT" "$@"
    result=$?
    # A child process cannot export into its parent. Read only our generated
    # path assignment after setup, without evaluating shell configuration.
    if (( result == 0 && refresh )) && [[ -r ${ZDOTDIR:-$HOME}/.zshrc ]]; then
        while IFS= read -r line; do
            case $line in
                '# >>> jrnl >>>') inside=1 ;;
                '# <<< jrnl <<<') inside=0 ;;
                'export JRNL_FILE='*)
                    if (( inside )); then
                        line=${line#export JRNL_FILE=}
                        export JRNL_FILE=${(Q)line}
                    fi ;;
            esac
        done < "${ZDOTDIR:-$HOME}/.zshrc"
    fi
    return $result
}
typeset -g _JRNL_WRAPPER=${functions[jrnl]}

# Capture literal text BEFORE zsh interprets redirection, globbing, history
# expansion or command substitutions. Only standalone jrnl input is changed.
_jrnl_literal_line() {
    emulate -L zsh
    local prefix text MATCH MBEGIN MEND
    local -a match mbegin mend
    unset _JRNL_HISTORY_LINE _JRNL_EXEC_LINE
    [[ ${CONTEXT:-start} == start ]] || return 0
    if [[ $BUFFER =~ '^([[:blank:]]*)jrnl[[:blank:]]+(.*)$' ]]; then
        # Finish ZLE's display while it still contains the user's original
        # command. The subsequent execution-only buffer is never redrawn.
        zle -I
        typeset -g _JRNL_HISTORY_LINE=$BUFFER
        # The escaped command name also keeps old escaped history replayable.
        prefix=$match[1]
        text=$match[2]
        if [[ $text =~ '^--[[:blank:]](.*)$' ]]; then
            text=$match[1]
            BUFFER="${prefix}\\jrnl -- ${(q)text}"
        else
            BUFFER="${prefix}\\jrnl ${(q)text}"
        fi
        typeset -g _JRNL_EXEC_LINE=$BUFFER
    fi
}

# Use zsh's history-context mechanism to retain the original line and discard
# only its escaped execution form. zsh restores the normal context afterwards.
_jrnl_add_history() {
    local original=${_JRNL_HISTORY_LINE-} executed=${_JRNL_EXEC_LINE-}
    unset _JRNL_HISTORY_LINE _JRNL_EXEC_LINE
    if [[ -n $executed && $1 == "$executed"$'\n' ]]; then
        if [[ ! -o histignorespace || $original != [[:blank:]]* ]]; then
            print -rs -- "$original"
        fi
        fc -p
    fi
    return 0
}

if [[ -o interactive ]]; then
    autoload -Uz add-zle-hook-widget add-zsh-hook
    zle -N _jrnl_literal_line
    add-zle-hook-widget line-finish _jrnl_literal_line
    add-zsh-hook zshaddhistory _jrnl_add_history
fi
