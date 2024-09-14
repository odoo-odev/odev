# ODEV

Automate common tasks relative to working with Odoo development databases.

<!-- TOC depthFrom:2 -->

-   [About](#about)
-   [Installation](#installation)
-   [Contributing](#contributing)
-   [Features](#features)
    -   [Commands](#commands)
    -   [Credentials](#credentials)

<!-- /TOC -->

## About

Odev is a multi-purpose tool designed for making the life of Odoo developers and support analysts easier.

It provides wrapper scripts around common tasks, speeding up the whole process of working with databases and allowing
shortcuts to otherwise lengthy commands.

## Installation

Make sure [Python 3.10 or higher](https://www.python.org/downloads/) is installed and available in your path.

Clone the [odev repository](https://github.com/odoo-odev/odev) to your computer and navigate to the `odev` folder:

```sh
git clone git@github.com:odoo-odev/odev.git && cd odev
```

Install the requirements through `pip`:

```sh
pip install --user -r requirements.txt
```

Run `setup.py` and follow the instructions displayed on screen:

```sh
python ./setup.py
```

That's it! You are ready to go, use `odev` from anywhere in your terminal to use it.

Odev will update itself automatically when new versions are available.

## Contributing

Submit a pull request to merge your development to the `main` branch. After review and proper testing, your feature will
be made available to all.

You have ideas to share but you don't want to dive in `odev`'s source code? No worries, you can also create a new
[issue](https://github.com/odoo-odev/odev/issues/new/choose) with the tags `bug` or `enhancement` to request a new
feature.

Check the [Contribution Guide](./docs/CONTRIBUTING.md) for more details about the contribution process.

## Features

### Commands

Odev works with subcommands, each having specific effects.

**Usage:** `odev <command> <args>`

Arguments in square brackets (`[arg]`) are optional and can be omitted, arguments in curvy brackets (`{arg}`) are
options to choose from, arguments without brackets (`arg`) are required.

To see the list of all commands run `odev help`.

To get help on a specific command and its usage, use `odev help <command>`.

### Plugins

Odev can be extended with plugins that are loaded from external GitHub repositories, they could be public or private to
your organizations and allow to add new features and commands or modify existing ones.

Plugins can be enabled with the predefined command `odev plugin --enable <plugin>`.

#### Known Plugins

| Name                                                                                          | Description                                                                                                  |
| --------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| [odoo-odev/odev-plugin-hosted](https://github.com/odoo-odev/odev-plugin-hosted)               | Interact with PaaS (odoo.sh) and SaaS (Odoo Online) databases, requires Odoo Technical Support access level. |
| [odoo-odev/odev-plugin-editor-vscode](https://github.com/odoo-odev/odev-plugin-editor-vscode) | Interact with VSCode, open a debugger session and configure workspaces.                                      |
| [odoo-odev/odev-plugin-export](https://github.com/odoo-odev/odev-plugin-export)               | Export customizations from a database and convert Studio to code.                                            |

### Credentials

To avoid inputting the credentials every time `odev` is run, symmetric encryption is used to store them. This is done
"automagically" with the help of an [`ssh-agent`](https://esc.sh/blog/ssh-agent-windows10-wsl2/)-loaded key. This means
that `ssh-agent` needs to be available in the shell environment the command is being run from, otherwise a warning will
be logged and credentials will need to be inputted every time. If you don't already have a custom script to launch
`ssh-agent`, we recommend using `keychain`, that's an easy option to do that and manage the different keys available
through `ssh-agent`.

After installing `keychain`, and depending on the shell of your choice, the following lines need to be added to the
`.bashrc`/`.zshrc`:

```sh
/usr/bin/keychain -q --nogui $HOME/.ssh/id_rsa
source $HOME/.keychain/$HOST-sh
```

**Alternatively**, you can save the following script into a new file under `~/.profile.d/start_ssh_agent` and make it
run automatically at startup by adding the line `source ~/.profile.d/start_ssh_agent` to your `~/.bashrc` or `~/.zshrc`
file.

```sh
#!/bin/sh

# ==============================================================================
# This script loads declared SSH keys into the running ssh-agent, launching it
# if necessary. This should ideally be sourced in the user's shell profile.
# ==============================================================================

env=~/.ssh/agent.env

# --- Declare the path to the keys to add to the agent -------------------------
declare -a keys=(
  "$HOME/.ssh/id_ed25519" # <-- Edit this line to load your own SSH key(s)
)

# --- Common methods and shortcuts ---------------------------------------------

agent_load_env() {
  test -f "$env" && . "$env" >| /dev/null
}

agent_start() {
  (umask 077; ssh-agent >| "$env")
  . "$env" >| /dev/null 2>&1
}

agent_add_key() {
  ssh-add $key >| /dev/null 2>&1
}

agent_add_keys() {
  for i in "${keys[@]}"; do
    ssh-add "$i" >| /dev/null 2>&1
  done
}

# --- Load the agent -----------------------------------------------------------

agent_load_env

# agent_run_state:
#   0: agent running with key
#   1: agent running without key
#   2: agent not running
agent_run_state=$(ssh-add -l >| /dev/null 2>&1; echo $?)

# --- Load the keys to the agent -----------------------------------------------

if [ ! "$SSH_AUTH_SOCK" ] || [ $agent_run_state = 2 ]; then
  agent_start
  agent_add_keys
elif [ "$SSH_AUTH_SOCK" ] && [ $agent_run_state = 1 ]; then
  agent_add_keys
fi

unset env

```
