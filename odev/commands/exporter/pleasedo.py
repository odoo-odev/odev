from odev.commands.exporter import scaffold
from odev.commands.odoo_db import quickstart, remove
from odev.exceptions import CommandAborted
from odev.structures import commands
from odev.utils import logging


_logger = logging.getLogger(__name__)


class PleaseDoCommand(commands.TemplateCreateDBCommand, commands.OdooComCliMixin):
    """
    Please do all the work for me :
        - Dump the database
        - Restore + Neutralize
        - Clone the repository if found
        - Scaffold your task
    """

    name = "pleasedo"
    database_required = True

    scaffold_args = [x for x in commands.ExportCommand.arguments if x["aliases"][0] != "path"]

    arguments = scaffold_args + [
        {
            "aliases": ["id"],
            "help": "Ps-tools or Odoo.com task id to generate",
        },
        {
            "aliases": ["-e", "--env"],
            "choices": ["prod", "staging"],
            "default": "prod",
            "help": "Default database to use (use staging for test)",
        },
        {
            "aliases": ["-d", "--db"],
            "metavar": "VERSION|PATH|URL",
            "dest": "source",
            "help": """
            One of the following:
                - an Odoo version number to create and init an empty database
                - a path to a local dump file to restore to a new database
                - a url to an Odoo SaaS or SH database to dump and restore locally
            """,
        },
        {
            "aliases": ["-r", "--reason"],
            "metavar": "reason",
            "help": "Fill the reason field when login with /_odoo/support",
        },
    ]

    def run(self):
        # TODO: Refactor and use the same method in restore that raise the exception
        if self.db_exists_all():
            if self.db_exists():
                _logger.warning(f"Database {self.database} already exists and is an Odoo database")

                if not _logger.confirm("Do you want to overwrite its content?"):
                    raise CommandAborted()

                remove.RemoveCommand.run_with(**self.args.__dict__)

        self.args.reason = self.args.reason if self.args.reason else f"Working on {self.args.id}"
        self.args.do_raise = False
        result = quickstart.QuickStartCommand.run_with(**self.args.__dict__)

        self.args.path = self.globals_context.get("repo_git_path", "") or "."
        result = result + scaffold.ScaffoldCommand.run_with(**self.args.__dict__)

        return result
