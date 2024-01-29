from typing import Any, Mapping

from odev.common.commands import DatabaseCommand
from odev.common.databases import LocalDatabase


class QuickStartCommand(DatabaseCommand):
    """Dump, restore and neutralize an existing database so that it can be used
    as a starting point for new custom developments.
    If possible, clone the repository containing existing customizations for
    the selected database.
    """

    name = "quickstart"
    aliases = ["qs"]

    arguments = [
        {
            "name": "name",
            "aliases": ["-n", "--name"],
            "help": "The name of the database to create locally, defaults to the name of the database dumped.",
        },
    ]

    _database_allowed_platforms = []

    @classmethod
    def prepare_command(cls, *args, **kwargs) -> None:
        super().prepare_command(*args, **kwargs)
        cls.import_arguments("dump", ["filestore"])
        cls.import_arguments("create", ["version"])
        cls.update_argument(
            "branch",
            {
                "help": """Branch to target for downloading a backup of PaaS (Odoo SH) instances.
                Also used as the branch to checkout after cloning the repository containing
                code customization for the selected database.
                """
            },
        )
        cls.update_argument(
            "version",
            {
                "help": """The Odoo version to use for the new database. If specified, a new database
                will be created from scratch instead of restoring a backup.
                """
            },
        )

    def run(self):
        branch_cli_argument = ["--branch", self.args.branch] if self.args.branch else []

        if self.args.version:
            self.odev.run_command("create", "--version", self.args.version, database=self.database)
        else:
            if self.args.filestore:
                branch_cli_argument.append("--filestore")

            self.odev.run_command("dump", *branch_cli_argument, database=self.database)
            self.odev.run_command(
                "restore",
                (self.odev.dumps_path / self.database._get_dump_filename(**self.get_dump_filename_kwargs())).as_posix(),
                "--no-neutralize",
                database=LocalDatabase(self.args.name or self.database.name),
            )

        self.odev.run_command("clone", *branch_cli_argument, database=self.database)
        self.odev.run_command("neutralize", database=LocalDatabase(self.args.name or self.database.name))

    def get_dump_filename_kwargs(self) -> Mapping[str, Any]:
        """Return the keyword arguments to pass to Database.get_dump_filename()."""
        return {
            "filestore": self.args.filestore,
            "suffix": self.database.platform.name,
            "extension": "zip",
        }
