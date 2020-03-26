# ODEV

Odoo development framework for automating common tasks related to Odoo custom
developments.

## Setup

Make sure [Python 3](https://www.python.org/download/releases/3.0/) is installed and available in your path.
Install the following requirements through `pip3`:

```sh
pip3 install --user clint psycopg2 getpass configparser subprocess gitpython tempfile zipfile
```

Clone the [odev repository](https://github.com/brinkflew/odev) to your computer and navigate to the `odev` folder:

```sh
git clone git@github.com:brinkflew/odev.git && cd odev
```

Run `setup.py` with root privileges and follow the instructions displayed on screen:

```sh
sudo ./setup.py
```

That's it! You are ready to go, use `odev` from anywhere in your terminal to use it.

---

## Update

Simply `git fetch && git pull` the repository again to update to the latest version.

You may have to rerun the `setup` if you didn't keep your local repository as install path, otherwise you are good to go!

---

## Try It!

Run `odev listing` from anywhere in your terminal to get a list of your local Odoo databases:

```sh
odev listing
```

```txt
+----------+----------+-------------------+-----+------+-----+--------------------------------------------------+
| Database | Status   | Versions          | PID | Port | URL | Filestore                                        |
+----------+----------+-------------------+-----+------+-----+--------------------------------------------------+
| test     | inactive | 12.0 (enterprise) |     |      |     | /home/brinkflew/.local/share/Odoo/filestore/test |
+----------+----------+-------------------+-----+------+-----+--------------------------------------------------+
[*] Exiting with code 0
```

---



## Docs

Arguments in square brackets (`[<arg>]`) are optional and can be omitted, arguments in angular brackets (`<arg>`) are required.

### Clean

Makes a local Odoo database suitable for development:

- Disables automated and scheduled actions
- Disables mails
- Set credentials for Administrator user  to **admin**:**admin**
- Extend database validity to December 2050

```sh
odev clean <database>
```

| Args     | Description                         |
|----------|-------------------------------------|
| database | Name of the local database to clean |

### Create

Creates a new, *empty*, local PostgreSQL database, not initialized with Odoo.

```sh
odev create <database>
```

| Args     | Description                                                                                          |
|----------|------------------------------------------------------------------------------------------------------|
| database | Name of the local database to create; the name is sanitized so that it can be used within PostgreSQL |

### Listing

Lists all the local Odoo databases. If a database is defined in PostgreSQL but not initialized with Odoo, it will not appear in this list.

```sh
odev listing
```

### Remove

Removes a local database from PostgreSQL and deletes its filestore.

```sh
odev remove <database>
```

| Args     | Description                          |
|----------|--------------------------------------|
| database | Name of the local database to remove |

### Rename

Renames a database and its filestore.

```sh
odev rename <database> <new_name>
```

| Args     | Description                                 |
|----------|---------------------------------------------|
| database | Name of the local database to rename        |
| new_name | New name for the database and its filestore |

### Restore

Restores an Odoo dump file to a local database and imports its filestore if present.
`.sql`, `.dump` and `.zip` files are supported.

```sh
odev restore <database> <dump_file>
```

| Args      | Description                                     |
|-----------|-------------------------------------------------|
| database  | Name of the local database to restore           |
| dump_file | Path to the dump file to import to the database |

### Run

Runs a local Odoo database, prefilling common addon paths and making sure the right version of Odoo is installed and in use.

If the version of Odoo required for the database is not present, downloads it and installs it locally. This is done by cloning the Odoo community, enterprise and design-themes repository multiple times to always keep a copy of each version on the computer. To save storage space, only one branch is cloned per version, keeping all other branches out of the history. This means that the sum of the sizes of all independant local versions should be lower (or roughly equal if all versions are installed) than the size of the entire Odoo repositories.

```sh
odev run <database> <addons> [<args>]
```

| Args     | Description                                                               |
|----------|---------------------------------------------------------------------------|
| database | Name of the local database to restore                                     |
| addons   | List of addon paths to add to the default ones, separated by a coma (`,`) |
| args     | Optional: additional args to pass to `odoo-bin`                           |

### Version

Gets the version of a local Odoo database.

```sh
odev version <database>
```

| Args     | Description                    |
|----------|--------------------------------|
| database | Database to get the version of |
