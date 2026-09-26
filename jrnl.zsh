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
    [[ ${CONTEXT:-start} == start ]] || return 0
    if [[ $BUFFER =~ '^([[:blank:]]*)jrnl[[:blank:]]+(.*)$' ]]; then
        # Escape the command name so recalled history is not quoted twice.
        prefix=$match[1]
        text=$match[2]
        if [[ $text == '-- '* ]]; then
            text=${text#-- }
            BUFFER="${prefix}\\jrnl -- ${(q)text}"
        else
            BUFFER="${prefix}\\jrnl ${(q)text}"
        fi
    fi
}

if [[ -o interactive ]]; then
    autoload -Uz add-zle-hook-widget
    zle -N _jrnl_literal_line
    add-zle-hook-widget line-finish _jrnl_literal_line
fi
