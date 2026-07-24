#!/usr/bin/env bash

# Developer setup for the Odev repository, run it after './install.sh'.
# End users never need this script.

script_dir="$(cd "$(dirname "$0")" && pwd)"
venv_python=~/.config/odev/venv/bin/python

if [ ! -x "$venv_python" ]; then
    echo "Odev is not installed yet. Run './install.sh' first"
    exit 1
fi

echo "[*] Installing development dependencies"
~/.config/odev/venv/bin/pip install -r "$script_dir/requirements-dev.txt"

if [ $? -ne 0 ]; then
    echo "Failed to install development dependencies"
    exit 1
fi

echo "[*] Enabling pre-commit hooks"
~/.config/odev/venv/bin/pre-commit install

if [ $? -ne 0 ]; then
    echo "Failed to enable pre-commit hooks"
    exit 1
fi

# Static analyzers resolve 'odev.plugins.<plugin>' through this symlink, it is gitignored, excluded from ruff,
# coverage and basedpyright, and hidden from the editor by '.vscode/settings.json'. Odev never uses it at runtime.
echo "[*] Linking the installed plugins into the repository for IDE support"
mkdir -p ~/.config/odev/plugins
ln -sfn "$HOME/.config/odev/plugins" "$script_dir/odev/plugins"

if [ $? -ne 0 ]; then
    echo "Failed to link the plugins directory into the repository"
    exit 1
fi

echo "Development setup complete"
