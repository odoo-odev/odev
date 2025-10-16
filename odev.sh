#!/bin/sh

# Run odev using the virtualenv if available, otherwise fallback to system python3
# for compatibility with older running installations of odev.

for interpreter in ~/.config/odev/venv/bin/python3 /usr/bin/python3; do
    if [ -x "$interpreter" ]; then
        exec "$interpreter" $(readlink -m $(dirname "$0"/..)/../main.py) "$@"
        exit $?
    fi
done

echo "No suitable python3 interpreter found" >&2
exit 1
