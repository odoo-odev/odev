#!/bin/sh

# Run odev using the virtualenv if available, otherwise fallback to system python3
# for compatibility with older running installations of odev.

resolve_path() {
    realpath "$1" 2>/dev/null || readlink -f "$1"
}

for interpreter in ~/.config/odev/venv/bin/python3 /usr/bin/python3; do
    if [ -x "$interpreter" ]; then
        SCRIPT_PATH=$(resolve_path "$0")
        exec "$interpreter" "$(dirname "$SCRIPT_PATH")/main.py" "$@"
        exit $?
    fi
done

echo "No suitable python3 interpreter found" >&2
exit 1
