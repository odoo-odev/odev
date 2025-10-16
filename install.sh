#!/usr/bin/env sh

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

echo "Setting up virtual environment"
mkdir -p ~/.config/odev
virtualenv -p "${python_executables[0]:-python3}" ~/.config/odev/venv > /dev/null 2>&1

if [ $? -ne 0 ]; then
    echo "Failed to create virtual environment"
    exit 1
fi

echo "Installing dependencies"
~/.config/odev/venv/bin/pip install -r requirements.txt > /dev/null 2>&1
~/.config/odev/venv/bin/pip install -r requirements-dev.txt > /dev/null 2>&1

find odev/plugins/*/ -type f -name 'requirements.txt' | while read reqfile; do
    ~/.config/odev/venv/bin/pip install -r "$reqfile" > /dev/null 2>&1
    if [ $? -ne 0 ]; then
        echo "Failed to install dependencies from $reqfile"
        exit 1
    fi
done

if [ $? -ne 0 ]; then
    echo "Failed to install dependencies"
    exit 1
fi

echo "Adding executable to available commands"
target_dir=""
for dir in ~/.local/bin /usr/local/bin; do
    abs_dir=$(eval echo "$dir")
    if echo "$PATH" | tr ':' '\n' | grep -qx "$abs_dir"; then
        target_dir="$abs_dir"
        break
    fi
done

if [ -n "$target_dir" ]; then
    if [ "$target_dir" = "/usr/local/bin" ]; then
        sudo ln -sf "$(pwd)/odev.sh" "$target_dir/odev"
    else
        ln -sf "$(pwd)/odev.sh" "$target_dir/odev"
    fi
else
    echo "No suitable directory found in PATH. Please add ~/.local/bin or /usr/local/bin to your PATH"
fi

if [ $? -ne 0 ]; then
    echo "Failed to add executable to PATH"
    exit 1
fi

echo "Installation complete. You can now run 'odev' from the command line"
