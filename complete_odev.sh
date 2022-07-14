# odev tab completion script
# Version:  0.3
# Install:  Link the script into /usr/share/bash-completions/completions/
#           or ~/.local/share/bash-completions/completions/
#           'source' the file to use the features in the current session.
# Features: Tab completion on commands, databases and filenames.
#           ?<TAB> at any point will display help on the current command and
#             redisplay the command line.
#           odev run -[i|u] <TAB> will offer directory names (modules) as options,
#             excluding ./util_package and ./psbe-internal.
#           odev run -[i|u] *<TAB> will put a csv of custom modules on the command line.

_odev ()   #  By convention, the function name starts with an underscore.
{
    _odev_complete_config="${HOME}/.config/odev/databases.cfg"

    _odev_complete_list_cache()
    {
        if [ "${_odev_complete_last:-0}" -lt "$(date +%s -r ${_odev_complete_config})" ]; then
            _odev_complete_list="$( odev list -1 )"
            _odev_complete_last="$(date +%s)"
        fi
    }

    local cur prev words cword split opts
    _init_completion -s || return

    if [ "$cur" = "?" ]; then
        cmd="${words[@]:0:cword} --help"
        $cmd
        # replace '?' and fake an option to force redraw-current-line after help text
        COMPREPLY=( " " "  " )
        return
    fi

    case ${COMP_CWORD} in
        1)
            # complete command names
            if [ -z "${_odev_complete_help}" ]; then
                _odev_complete_help="$( odev help -1 )"
            fi
            opts=${_odev_complete_help}
            ;;
        2)
            # complete database names
            _odev_complete_list_cache
            opts=${_odev_complete_list}
            ;;
        3)
            # complete template names
            if [ "${words[1]}" = "create" ]; then
                _odev_complete_list_cache
                opts=${_odev_complete_list}
            fi
            ;;
        4)
            # complete custom module/directory names
            if [ "$prev" = "-i" -o "$prev" = "-u" ]; then
                # glob on './*' to avoid any '.*' files/dirs
                opts=( ./* )
                for o in "${!opts[@]}"; do
                    # remove files or special directories
                    if [ ! -d ${opts[o]} -o "${opts[o]}" = "./util_package" -o "${opts[o]}" = "./psbe-internal" ]; then
                        unset opts[o]
                    else
                        # removing leading ./
                        opts[$o]=${opts[o]#./}
                    fi
                done
                # convert array to wordlist
                opts="${opts[@]}"
                # replace '*' with a csv of all module names
                if [ "$cur" = "*" ]; then
                    COMPREPLY=( $( echo "${opts}" | tr ' ' ',' ) )
                    return
                fi
            fi
            ;;
        *)
            _filedir
            return
    esac

    COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )

    return
} &&
complete -F _odev -o default odev
