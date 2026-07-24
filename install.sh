#!/usr/bin/env bash

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 is not installed. Please install Python 3 and try again"
    exit 1
fi

if ! command -v virtualenv >/dev/null 2>&1; then
    echo "virtualenv is not installed. Please install virtualenv and try again"
    exit 1
fi

declare -a python_executables
while IFS= read -r -d $'\0' line; do
    python_executables+=("$line")
done < <(
    for p in $(echo "$PATH" | tr ':' '\n'); do
        if [[ "$p" == /usr/* || "$p" == $HOME/* ]]; then
            find "$p" -type f -executable -regex '.*python3\.[0-9]+' -print0 2>/dev/null
        fi
    done
)

# Sort python_executables by version in descending order
IFS=$'\n' python_executables=($(for p_exec in "${python_executables[@]}"; do echo "$(basename "$p_exec" | sed -n 's/.*python3\.\([0-9]\+\)/\1/p') $p_exec"; done | sort -rn | cut -d' ' -f2- | uniq))
unset IFS

echo "[*] Setting up virtual environment"
mkdir -p ~/.config/odev
virtualenv -p "${python_executables[0]:-python3}" ~/.config/odev/venv

if [ $? -ne 0 ]; then
    echo "Failed to create virtual environment"
    exit 1
fi

echo "[*] Creating plugins directory"
mkdir -p ~/.config/odev/plugins

echo "[*] Installing dependencies"
~/.config/odev/venv/bin/pip install -r requirements.txt
~/.config/odev/venv/bin/pip install -r requirements-dev.txt

find -L ~/.config/odev/plugins -type f -name 'requirements.txt' | while read -r reqfile; do
    ~/.config/odev/venv/bin/pip install -r "$reqfile"

    if [ $? -ne 0 ]; then
        echo "Failed to install dependencies from $reqfile"
        exit 1
    fi
done

echo "[*] Adding executable to available commands"
target_dir=""
use_sudo=false
for dir in $(echo "$PATH" | tr ':' '\n'); do
    if [[ -d "$dir" && -w "$dir" && ("$dir" == /usr/* || "$dir" == "$HOME"/*) ]]; then
        target_dir="$dir"
        break
    fi
done

if [ -z "$target_dir" ]; then
    for dir in $(echo "$PATH" | tr ':' '\n'); do
    if [[ -d "$dir" && "$dir" == /usr/* ]]; then
        target_dir="$dir"
        use_sudo=true
        echo "You might be prompted for your password to create a symlink in $target_dir"
        break
    fi
done
fi

if [ -n "$target_dir" ]; then
    if $use_sudo; then
        sudo ln -sf "$(pwd)/odev.sh" "$target_dir/odev"
    else
        ln -sf "$(pwd)/odev.sh" "$target_dir/odev"
    fi

    if [ $? -ne 0 ]; then
        echo "Failed to add executable to PATH"
        exit 1
    fi
else
    echo "No suitable directory found in PATH. Please add ~/.local/bin or /usr/local/bin to your PATH"
    exit 1
fi

if [ $? -ne 0 ]; then
    echo "Failed to add executable to PATH"
    exit 1
fi

echo "[*] Installation complete. You can now run 'odev' from the command line"
