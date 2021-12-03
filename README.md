# ODEV

Automate common tasks relative to working with Odoo development databases.

<!-- TOC depthFrom:2 -->

- [About](#about)
- [Contributing](#contributing)
- [Installation](#installation)
- [Updates](#updates)
- [Try It!](#try-it)
- [Commands](#commands)

<!-- /TOC -->

## About

Odev is a multi-purpose tool destined at making the life of PS-Tech developers easier.

It provides wrapper scripts around common tasks, speeding up the whole process of working with databases and allowing shortcuts to otherwise lengthy commands.

## Contributing

### Want to improve Odev?

Create your own branch from `psbe-ps-tech-tools/odev` then submit a pull request to merge your development to the `odev` branch. After review and proper testing, your feature will be made available to all.

### Track other `odev` development branches

If you want to participate in developing or testing new features on already existing forked branches, you can track all `odev` branches with

```sh
git config remote.origin.fetch "+refs/heads/odev*:refs/remotes/origin/odev*"
git fetch --all
```

### Found a bug?

Either fix it in a new branch and create a pull request, or submit an issue on GitHub explaining what happened, how to reproduce it and what was the expected result.

## Installation

Make sure [Python 3](https://www.python.org/download/releases/3.0/) is installed and available in your path.

Clone the [odev repository](https://github.com/odoo-ps/psbe-ps-tech-tools/tree/odev) to your computer and navigate to the `odev` folder:

```sh
git clone --single-branch --branch odev git@github.com:odoo-ps/psbe-ps-tech-tools.git odev && cd odev
```

Install the requirements through `pip3`:

```sh
pip3 install --user -r requirements.txt
```

Run `setup.py` and follow the instructions displayed on screen:

```sh
./setup.py
```

That's it! You are ready to go, use `odev` from anywhere in your terminal to use it.

---

## Updates

Odev will automatically check for updates and ask whether you want to install them at each run.

If you want to manually fetch updates, simply `git fetch && git pull` the repository to update to the latest version.

You may have to rerun the `setup` if you didn't keep your local repository as install path, otherwise you are good to go!

---

## Try It!

Run `odev list` from anywhere in your terminal to get a list of your local Odoo databases:

```sh
odev list
```

```txt
       Name         Version             URL
  =========================================
   ⬤   odev_test    14.0 - enterprise
   ⬤   my_odoo_db   15.0 - enterprise
```

---

## Commands

**Usage:** `odev <command> <args>`

Arguments in square brackets ([arg]) are optional and can be omitted,
arguments in curvy brackets ({arg}) are options to choose from,
arguments without brackets (arg) are required.

To get help on a specific command and its usage, use `odev help <command>`

Odev provides the following commands:

### `clean`

Render a local Odoo database suitable for development:
  - Disable automated and scheduled actions
  - Disable mails
  - Set credentials for the Administrator user to `admin`:`admin`
  - Set password for the first 50 users to `odoo`
  - Extend database validity to December 2050 and remove enterprise code
  - Set report.url and web.base.url to `http://localhost:8069`
  - Disable Oauth providers

### `cloc`

Count the lines of code in custom modules.

### `create`

Create a new empty local PostgreSQL database without initializing it with Odoo.
Effectively a wrapper around `pg_create` with extra checks.

### `dump`

Download a dump of a SaaS or SH database and save it locally.
You can choose whether to download the filestore or not.

### `get`

Get a config parameter as used within odev.

### `help`

Display extensive help about the selected command or a generic help message lightly covering all available commands.

### `init`

Initialize an empty PSQL database with the base version of Odoo for a given major version.

### `kill`

Kill a running Odoo database. Useful if the process crashed because of a forgotten IPDB or if you lost your terminal and don't want to search for the process' PID.

### `list`

List all Odoo databases on this computer. If a database is defined in PostgreSQL but not initialized with Odoo, it will not be listed here.

A pattern can optionally be provided to filter databases based on their name.

### `quickstart`

Quickly setup a local database and start working with it directly.

This command performs the following actions:
  - Create a new, empty database
  - Initialize, dump and restore or restore an existing dump
  - Clean the database so that it can be used for development

### `rebuild`

Launch a rebuild of a branch on Odoo SH.

### `remove`

Drop a local database in PostgreSQL and delete its Odoo filestore on disk.

### `rename`

Rename a local database and move its filestore to the corresponding path.

### `restore`

Restore an Odoo dump file to a local database and import its filestore if present. '.sql', '.dump' and '.zip' files are supported.

### `run`

Run a local Odoo database, prefilling common addon paths and making sure the right version of Odoo is installed and in use.

If the version of Odoo required for the database is not present, download and install it locally.
This is done by cloning the Odoo community, enterprise and design-themes repositories
multiple times (once per version) to always keep a copy of each version on the computer.
To save storage space, only one branch is cloned per version, keeping all other branches out of the history.

### `set`

Set a config parameter to use within odev.

Valid key-value pairs are defined as follows:
  - logger.theme: Theme to use for Odev's logger (minimal|extended)
  - path.odoo: Local path to where odoo files are stored
  - path.dump: Local path to where dump files are stored when downloaded through Odev
  - path.dev: Local path to where custom development repositories are located

### `shell`

Open the Odoo shell for a local database.

### `test`

Run tests on a local Odoo database.

### `upgrade-build`

TODO: Missing command description

### `upgrade-manual`

Manually run 'odoo-bin' on SH to install / upgrade the specified modules, copying the required 'util' files beforehand.
Useful to run migrations right after having uploaded a dump on the branch.

### `upgrade-merge`

Prepares the SH branch to run automatic upgrades with `util` support for merging a PR / pushing commits, and cleans up after it's done.
Directly handles the PR merge.

### `upgrade-wait`

Prepares the SH branch to run automatic upgrades with `util` support and waits for a new SH build to complete, then cleans up when it's done.
Useful for handling all other build cases (webhook redeliver, generic push).

### `upload`

Command class for uploading and importing a database dump on a Odoo SH branch.
Uploads a .zip database dump to an Odoo SH branch.

### `version`

Get the Odoo version on which a local database is running.
