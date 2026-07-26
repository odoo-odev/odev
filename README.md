# ODEV

Automate common tasks relative to working with Odoo development databases.

## About

Odev is a multi-purpose tool designed for making the life of Odoo developers and support analysts easier.

It provides wrapper scripts around common tasks, speeding up the whole process of working with databases and allowing
shortcuts to otherwise lengthy commands.

## Documentation

Full documentation for all commands and features is available in the [Odev Wiki](https://github.com/odoo-odev/odev/wiki).

## Requirements

Before you can run this tool, make sure the below requirements are set on your system:

- [Python **3.10.12** or higher](https://www.python.org/downloads/) (3.12+ is recommended)
- Python's [virtualenv](https://virtualenv.pypa.io/en/latest/) module (this is **not** python3-venv)
- [PostgreSQL](https://www.odoo.com/documentation/19.0/administration/on_premise/source.html#prepare) as from Odoo's
  source install requirements
- [Other Odoo dependencies](https://www.odoo.com/documentation/19.0/administration/on_premise/source.html#dependencies)

Odoo builds part of its Python dependencies (`gevent`, `lxml`, `python-ldap`, …) from source, which needs a C compiler
and the matching development packages: the headers of the Python version Odoo runs on, the PostgreSQL client library
and the OpenLDAP and SASL headers. On Debian and Ubuntu, install them all from the Odoo sources Odev has cloned:

```sh
sudo ~/odoo/repositories/odoo/odoo/setup/debinstall.sh
```

On Fedora, Arch, openSUSE, Alpine or macOS, install the equivalents with your own package manager. Odev checks
whenever it creates a virtual environment for a version of Odoo and, whatever the system, tells you what is missing
along with the command that installs it. It never installs anything itself.

Make sure `git` is properly setup with SSH key authentication before using commands, as Odev will try to connect to
the Odoo [Community](https://github.com/odoo/odoo) and [Enterprise](https://github.com/odoo/enterprise) repositories
to pull sources when required.

## Installation

Clone the [odev repository](https://github.com/odoo-odev/odev) to your computer and navigate to the `odev` folder:

```sh
git clone https://github.com/odoo-odev/odev.git && cd odev
```

Run the install script:

```sh
./install.sh
```

Run `odev setup` to configure `odev`:

```sh
odev setup
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
