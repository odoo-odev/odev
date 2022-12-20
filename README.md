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

Make sure [Python 3.8 or higher](https://www.python.org/downloads/) is installed and available in your path.

Clone the [odev repository](https://github.com/odoo-ps/ps-tech-odev) to your computer and navigate to the `ps-tech-odev`
folder:

```sh
git clone --single-branch --branch main git@github.com:odoo-ps/ps-tech-odev.git && cd ps-tech-odev
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
[issue](https://github.com/odoo-ps/ps-tech-odev/issues/new/choose) with the tags `bug` or `enhancement` to request a new
feature.

Check the [Contribution Guide](./CONTRIBUTING.md) for more details about the contribution process.

## Features

### Commands

Odev works with subcommands, each having specific effects.

**Usage:** `odev <command> <args>`

Arguments in square brackets ([arg]) are optional and can be omitted, arguments in curvy brackets ({arg}) are options to
choose from, arguments without brackets (arg) are required.

To see the list of all commands run `odev help`.

To get help on a specific command and its usage, use `odev help <command>`.

### Credentials

To avoid inputting the credentials every time `odev` is run, symmetric encryption is used to store them. This is done
"automagically" with the help of an `ssh-agent`-loaded key. This means that `ssh-agent` needs to be available in the
shell environment the command is being run from (it's also required to use `odev sh` commands for SSH connectivity to
odoo.sh builds through a github key pair), otherwise a warning will be logged and credentials will need to be inputted
every time. If you don't already have a custom script to launch `ssh-agent`, we recommend using `keychain`, that's an
easy option to do that and manage the different keys available through
[`ssh-agent`](https://esc.sh/blog/ssh-agent-windows10-wsl2/).

After installing `keychain`, and depending on the shell of your choice, the following lines need to be added to the
`.bashrc`/`.zshrc`:

```sh
/usr/bin/keychain -q --nogui $HOME/.ssh/id_rsa
source $HOME/.keychain/$HOST-sh
```
