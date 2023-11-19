#/usr/bin/env bash

__complete() {
    COMPREPLY=($(dts --complete "$COMP_CWORD" "${COMP_WORDS[@]}"));
};

complete -F __complete -o default dts
