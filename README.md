# ODEV

Odoo development framework for automating common tasks related to Odoo custom
developments.

<!-- TOC depthFrom:2 -->

- [Install](#install)
- [Update](#update)
- [Try It!](#try-it)
- [Docs](#docs)
  - [Clean](#clean)
  - [Create](#create)
  - [Dump](#dump)
  - [Init](#init)
  - [Kill](#kill)
  - [List](#list)
  - [Quickstart](#quickstart)
  - [Remove](#remove)
  - [Rename](#rename)
  - [Restore](#restore)
  - [Run](#run)
  - [Version](#version)
- [Examples](#examples)
  - [Restore an existing dump to a new local database](#restore-an-existing-dump-to-a-new-local-database)
  - [Launch a local database](#launch-a-local-database)
  - [Kill a running database](#kill-a-running-database)
  - [Delete a local database to save disk space](#delete-a-local-database-to-save-disk-space)
  - [Dump a SaaS database and restores it in a new local database in one command](#dump-a-saas-database-and-restores-it-in-a-new-local-database-in-one-command)
  - [List local databases and display their version and status](#list-local-databases-and-display-their-version-and-status)
  - [Create a fresh, empty database in Odoo 12.0](#create-a-fresh-empty-database-in-odoo-120)

<!-- /TOC -->

## Install

Make sure [Python 3](https://www.python.org/download/releases/3.0/) is installed and available in your path.
Install the following requirements through `pip3`:

```sh
pip3 install --user clint psycopg2 configparser gitpython
```

Clone the [odev repository](https://github.com/brinkflew/odev) to your computer and navigate to the `odev` folder:

```sh
git clone git@github.com:brinkflew/odev.git && cd odev
```

Run `setup.py` and follow the instructions displayed on screen:

```sh
./setup.py
```

That's it! You are ready to go, use `odev` from anywhere in your terminal to use it.

---

## Update

Simply `git fetch && git pull` the repository again to update to the latest version.

You may have to rerun the `setup` if you didn't keep your local repository as install path, otherwise you are good to go!

---

## Try It!

Run `odev list` from anywhere in your terminal to get a list of your local Odoo databases:

```sh
odev list
```

```txt
[i] Listing local Odoo databases...
 ⬤  test ..................... (13.0 - enterprise)
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
- Set password for all other users to **odoo**
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
odev create <database> [<template>]
```

| Args     | Description                                                                                          |
|----------|------------------------------------------------------------------------------------------------------|
| database | Name of the local database to create; the name is sanitized so that it can be used within PostgreSQL |
| template | Optional: name of an existing PostgreSQL database to copy                                            |

### Dump

Downloads a dump of a SaaS or SH database and saves it to your computer. Lets you choose whether to download the filestore or not.

```sh
odev dump <database> <url> <dest>
```

| Args     | Description                                                                                                                  |
|----------|------------------------------------------------------------------------------------------------------------------------------|
| database | Name of the database, this is only used in the name of the downloaded dump file and doesn't have to match an actual database |
| url      | URL to the database to dump, in the form of `https://db.odoo.com`. The protocol part (`http/s://`) can be omitted.           |
| dest     | Directory to which the dumped file will be saved once downloaded                                                             |

### Init

Initializes an empty PSQL database with a basic version of Odoo. Basically, installs the base module on an empty DB.

```sh
odev init <database> <version>
```

| Args     | Description                                                      |
|----------|------------------------------------------------------------------|
| database | Name of the local database to initialize                         |
| version  | Odoo version to use; must correspond to an Odoo community branch |

### Kill

Kills a running Odoo database. Useful if the process crashed because of a forgotten IPDB or if you lost your terminal and don't want to search for the process' PID.

```sh
odev kill <database>
```

| Args     | Description                                       |
|----------|---------------------------------------------------|
| database | Name of the local database to kill the process of |

### List

Lists all the local Odoo databases. If a database is defined in PostgreSQL but not initialized with Odoo, it will not appear in this list.

```sh
odev list
```

### Quickstart

~~Summons a quickstart consultant.~~ Quickly and easlily setups a database.
This performs the following actions:

- Creates a new, empty database
- Initializes, dumps and restores or restores an existing dump to the new database
- Cleanses the database so that it can be used for development

```sh
odev quickstart <database> <version|path|url>
```

| Args               | Description                                       |
|--------------------|---------------------------------------------------|
| database           | Name of the local database to create              |
| version\|path\|url | If a version number, calls `odev init`; If a path to a local file, attempts to restore it to the database (the file must be a valid database dump); If a URL to an Odoo SaaS or SH database, downlaods a dump of it and restores it locally |

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
odev run <database> <addons> [<options>]
```

| Args     | Description                                                               |
|----------|---------------------------------------------------------------------------|
| database | Name of the local database to restore                                     |
| addons   | List of addon paths to add to the default ones, separated by a coma (`,`) |
| options  | Optional: additional arguments to pass to `odoo-bin`                      |

### Version

Gets the version of a local Odoo database.

```sh
odev version <database>
```

| Args     | Description                    |
|----------|--------------------------------|
| database | Database to get the version of |

## Examples

Here are a few 'common' examples of what you can do using `odev`.

### Restore an existing dump to a new local database

```txt
$ odev create testdb
[i] Creating database testdb
[i] Created database testdb
[*] Exiting with code 0

$ odev restore testdb /odoo/dumps/testdb/testdb.dump.zip
[i] Restoring dump file '/odoo/dumps/testdb/testdb.dump.zip' to database testdb
[!] This may take a while, please be patient...
[i] Filestore detected, installing to /home/brinkflew/.local/share/Odoo/filestore/testdb/
[i] Importing SQL data to database testdb
[*] Exiting with code 0

$ odev clean testdb
[i] Cleaning database testdb
[i] Cleaned database testdb
[i] Login to the administrator account with the credentials 'admin:admin'      
[i] Login to any other account with their email address and the password 'odoo'
[*] Exiting with code 0
```

### Launch a local database

```txt
$ odev run testdb /odoo/dev/psbe-testdb -u testmodule --dev=xml
[i] Checking for updates in Odoo Community version 13.0
[*] Up to date!
[i] Checking for updates in Odoo Enterprise version 13.0
[*] Up to date!
[i] Checking for updates in Odoo Design Themes version 13.0
[*] Up to date!
[i] Running: /odoo/versions/13.0/odoo/odoo-bin -d testdb --addons-path=/odoo/versions/13.0/enterprise,/odoo/versions/13.0/design-themes,/odoo/versions/13.0/odoo/odoo/addons,/odoo/versions/13.0/odoo/addons,/odoo/dev/psbe-testdb -u testmodule --dev=xml
2020-09-14 12:29:23,186 25776 INFO ? odoo: Odoo version 13.0
[...]
```

### Kill a running database

```txt
$ odev kill testdb
[i] Stopping database testdb
[*] Exiting with code 0
```

*In the terminal in which the database was running:*

```txt
[...]
2020-09-14 12:40:21,278 26655 INFO testdb odoo.modules.loading: loading 216 modules...
2020-09-14 12:40:24,943 26655 INFO testdb odoo.modules.loading: 216 modules loaded in 3.66s, 0 queries
2020-09-14 12:40:26,447 26655 INFO testdb odoo.modules.loading: Modules loaded.
[*] Exiting with code -9
```

### Delete a local database to save disk space

```txt
$ odev rm testdb
[!] You are about to delete the database testdb and its filestore. This action is irreversible.
[?] Delete database 'testdb' and its filestore? [y/n] y
[i] Deleting PSQL database testdb
[i] Deleted database
[i] Attempting to delete filestore in '/home/brinkflew/.local/share/Odoo/filestore/testdb'
[i] Deleted filestore from disk
[*] Exiting with code 0
```

### Dump a SaaS database and automatically restore it in a new local database in one command

```txt
$ odev quickstart testdb test.odoo.com
[i] Creating database testdb
[i] Created database testdb
[i] Logging you in to https://test.odoo.com support console
[?] Login: avs
[?] Password:
[?] Reason (optional):
[*] Successfuly logged-in to https://test.odoo.com/_odoo/support
[i] About to download dump file for https://test.odoo.com
[?] Do you wish to include the filestore? [y/n] y
[i] Downloading dump from https://test.odoo.com/saas_worker/dump.zip to /tmp/odev/20200912_testdb.dump.zip...
[!] This may take a while, please be patient...
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
100  574M  100  574M    0     0  2545k      0  0:03:51  0:03:51 --:--:-- 4120k
[*] Successfuly downloaded dump file
[i] Restoring dump file '/tmp/odev/20200912_testdb.dump.zip' to database testdb
[!] This may take a while, please be patient...
[i] Filestore detected, installing to /home/brinkflew/.local/share/Odoo/filestore/testdb/
[i] Importing SQL data to database testdb
[i] Cleaning database testdb
[i] Cleaned database testdb
[i] Login to the administrator account with the credentials 'admin:admin'
[i] Login to any other account with their email address and the password 'odoo'
[*] Exiting with code 0
```

### List local databases and display their version and status

***Note:** Circles will be colored in your terminal. With `testdb` being the only database currently running, its circle will be displayed in green. Other databases are stopped and will be shown in red.*

```txt
$ odev ls
[i] Listing local Odoo databases...
 ⬤  clientdb ................. (12.0 - enterprise)
 ⬤  presales ................. (13.0 - enterprise)
 ⬤  testdb ................... (13.0 - enterprise) [http://localhost:8069/web]
[*] Exiting with code 0
```

### Create a fresh, empty database in Odoo 12.0

```txt
$ odev qs freshdb 12.0
[i] Creating database freshdb
[i] Created database freshdb
[i] Checking for updates in Odoo Community version 12.0
[*] Up to date!
[i] Checking for updates in Odoo Enterprise version 12.0
[*] Up to date!
[i] Checking for updates in Odoo Design Themes version 12.0
[*] Up to date!
[i] Running: /odoo/versions/12.0/odoo/odoo-bin -d freshdb --addons-path=/odoo/versions/12.0/enterprise,/odoo/versions/12.0/design-themes,/odoo/versions/12.0/odoo/odoo/addons,/odoo/versions/12.0/odoo/addons -i base --stop-after-init
2020-09-14 12:57:50,445 29016 INFO ? odoo: Odoo version 12.0
2020-09-14 12:57:50,447 29016 INFO ? odoo: addons paths: ['/home/brinkflew/.local/share/Odoo/addons/12.0', '/odoo/versions/12.0/enterprise', '/odoo/versions/12.0/design-themes', '/odoo/versions/12.0/odoo/odoo/addons', '/odoo/versions/12.0/odoo/addons']
[...]
2020-09-14 12:58:17,360 29016 INFO freshdb odoo.modules.loading: 15 modules loaded in 9.31s, 0 queries
2020-09-14 12:58:17,515 29016 INFO freshdb odoo.modules.loading: Modules loaded.
2020-09-14 12:58:17,519 29016 INFO freshdb odoo.service.server: Initiating shutdown
2020-09-14 12:58:17,530 29016 INFO freshdb odoo.service.server: Hit CTRL-C again or send a second signal to force the shutdown.
[*] Exiting with code 0
```

### Download a dump of an Odoo SH database without its filestore

***Note:** This also works with SaaS databases.*

```txt
$ odev dump testsh https://testsh.odoo.com ~/odev/dumps/test/
[i] Logging you in to https://testsh.odoo.com support console
[?] Login: avs
[?] Password: 
[?] Reason (optional): 
[*] Successfuly logged-in to https://testsh.odoo.com/_odoo/support?token=585eb245f775907cda8b6c904f2e63f8
[i] About to download dump file for testsh
[?] Do you want to include the filestore? [y/n] n
[i] Downloading dump from eupp5.odoo.com/_long/paas/build/000001/dump.sql.gz?token=585eb245f775907cda8b6c904f2e63f8 to /home/avs/odev/dumps/test//20201010_testsh.dump.sql.gz...
[!] This may take a while, please be patient...
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
100   169  100   169    0     0   2913      0 --:--:-- --:--:-- --:--:--  2913
100 2316k    0 2316k    0     0  1150k      0 --:--:--  0:00:02 --:--:-- 1336k
[*] Successfuly downloaded dump file
[*] Exiting with code 0
```
