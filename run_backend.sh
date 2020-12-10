#!/usr/bin/env bash

# This script simply runs multiple scanner backend using the backend information provided from stdin.

while IFS= read -r line;
do
    kb_info=($line)
    if [[ ${kb_info[0]} = "#" ]]
    then
        continue
    else
        gunicorn "-b" ${kb_info[1]:7:14} 'swh.scanner.backend:create_app("'${kb_info[2]}'")' &
    fi

done
