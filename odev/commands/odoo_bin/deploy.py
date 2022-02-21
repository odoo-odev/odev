"""Deploys a SaaS module to a local or remote Odoo database."""

import os
import re
import shlex
import subprocess
from argparse import Namespace

from git import Repo

from odev.constants import ODOO_MANIFEST_NAMES
from odev.exceptions import InvalidOdooModule, MissingOdooDependencies
from odev.structures import commands
from odev.utils import logging
from odev.utils.signal import capture_signals


_logger = logging.getLogger(__name__)


re_url = re.compile(r"^https?://")
re_path = re.compile(r"(\\|/)")
re_version = re.compile(r"^(\d{2}\.\d)")
re_password = re.compile(r"--password\s[^\s]+")
re_error = re.compile(r"Error", re.IGNORECASE)
re_dependencies = re.compile(r"Unmet module dependencies:")
re_import_module = re.compile(r"does not have the \'base_import_module\' installed")

LOGIN = "--login"
PASSWORD = "--password"
FORCE_UPDATE = "--force"
VERIFY_SSL = "--verify-ssl"


class DeployCommand(commands.LocalDatabaseCommand):
    """
    Deploy a local module to a SaaS database, or a local database if no URL is provided.
    """

    name = "deploy"
    odoobin_subcommand = "deploy"
    database_required = False
    arguments = [
        {
            "aliases": ["url"],
            "nargs": "?",
            "help": "Optional URL of a SaaS database to upload the module to",
        },
        {
            "aliases": ["path"],
            "help": "Path to the module to deploy (must be a valid Odoo module)",
        },
        {
            "aliases": [LOGIN],
            "nargs": "?",
            "help": "Login (default: admin)",
        },
        {
            "aliases": [PASSWORD],
            "nargs": "?",
            "help": "Password (default: admin)",
        },
        {
            "aliases": [VERIFY_SSL],
            "dest": "verify_ssl",
            "action": "store_true",
            "help": "Verify SSL certificate",
        },
        {
            "aliases": [FORCE_UPDATE],
            "dest": "force_update",
            "action": "store_true",
            "help": 'Force init even if the module is already installed, will update records with `noupdate="1"`',
        },
    ]

    def __init__(self, args: Namespace):
        if re_url.match(args.database):
            args.url = args.database
            args.database = None

        super().__init__(args)
        self.path = args.path
        self.url = args.url and self.sanitize_url(f"{'https://' if not re_url.match(args.url) else ''}{args.url}")
        self.login = args.login or _logger.ask('Login (blank for "admin"):')
        self.password = args.password or _logger.password('Password (blank for "admin"):')

        if not self.database and args.database:
            self.database: str = args.database

    def sanitize_url(self, url, remove_after=".odoo.com"):
        return url[: url.index(remove_after) + len(remove_after)]

    def run(self):
        """
        Deploy a local module to a SaaS database, or a local database if no URL
        is provided.
        """

        if not any(os.path.isfile(os.path.join(self.path, mname)) for mname in ODOO_MANIFEST_NAMES):
            raise InvalidOdooModule(f"{self.path} is not an Odoo module")

        odoodir = self.config["odev"].get("paths", "odoo")

        try:
            repo = Repo(os.path.join(self.path, ".."))
            branch = repo.active_branch.name
            version_match = re_version.findall(branch)
        except Exception:
            version_match = False

        if version_match:
            version = version_match[~0]
        else:
            version_dirs = sorted(os.listdir(odoodir))
            version = (
                version_match[~0]
                if version_match
                else _logger.ask(
                    "Couldn't guess version from local repository, "
                    "what Odoo version is the target database running on?",
                    version_dirs[~0],
                )
            )

        assert version
        odoodir = os.path.join(odoodir, version)
        odoobin = os.path.join(odoodir, "odoo/odoo-bin")

        python_exec = os.path.join(odoodir, "venv/bin/python")
        command_args = [
            python_exec,
            odoobin,
            self.odoobin_subcommand,
            self.path,
        ]

        if self.database:
            self.check_database()
            command_args += ["--db", self.database]

        if self.url:
            command_args.append(self.url)

        if self.login:
            command_args += [LOGIN, self.login]

        if self.password:
            command_args += [PASSWORD, self.password]

        if self.args.verify_ssl:
            command_args.append(VERIFY_SSL)

        if self.args.force_update:
            command_args.append(FORCE_UPDATE)

        command = shlex.join(command_args)
        _logger.info(f"""Running: {re_password.sub(f'{PASSWORD} {"*" * len(self.password or "admin")}', command)}""")

        with capture_signals():
            module_name = os.path.basename(os.path.normpath(self.path))
            result = subprocess.getoutput(command)
            error_match = re_error.search(result)

            if error_match:
                if re_import_module.search(result) or re_dependencies.search(result):
                    error_desc = result[error_match.span()[~0] :]
                    error_desc = re.sub(r"^(\W\s)+?", "", error_desc)
                    error_desc = re.sub(r"\.$", "", error_desc)
                    raise MissingOdooDependencies(error_desc)
                else:
                    raise InvalidOdooModule(
                        "Cannot install module: either the supplied credentials " "or the imported module are invalid"
                    )

            _logger.success(f"Successfully deployed module `{module_name}` to {self.url or self.database}")

        return 0
