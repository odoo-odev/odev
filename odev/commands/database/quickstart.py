from typing import Any, MutableMapping

from odev.common import args
from odev.common.commands import DatabaseCommand
from odev.common.databases import LocalDatabase


class QuickStartCommand(DatabaseCommand):
    """Dump, restore and neutralize an existing database so that it can be used
    as a starting point for new custom developments.
    If possible, clone the repository containing existing customizations for
    the selected database.
    """

    _name = "quickstart"
    _aliases = ["qs"]

    new_name = args.String(
        name="name",
        aliases=["-n", "--name"],
        description="The name of the database to create locally, defaults to the name of the database dumped.",
    )
    branch = args.String(
        description="""Branch to target for downloading a backup of PaaS (Odoo SH) instances.
        Also used as the branch to checkout after cloning the repository containing
        code customization for the selected database.
        """,
    )
    version = args.String(
        aliases=["-V", "--version"],
        description="""The Odoo version to use for the new database. If specified, a new database
        will be created from scratch instead of downloading and restoring a backup.
        """,
    )
    filestore = args.Flag(
        aliases=["-F", "--filestore"],
        description="Include the filestore when downloading a backup of the database.",
    )

    _database_allowed_platforms = []
    _database_exists_required = False

    def run(self):
        passthrough_args = ["--branch", self.args.branch] if self.args.branch else []

        if self.args.version:
            self.odev.run_command("create", "--version", self.args.version, database=self._database)
        else:
            self.odev.run_command("clone", *passthrough_args, database=self._database)
            dumped = self.odev.run_command(
                "dump",
                *(passthrough_args + (["--filestore"] if self.args.filestore else [])),
                database=self._database,
            )

            dump_file = self.odev.dumps_path / self._database._get_dump_filename(**self.get_dump_filename_kwargs())

            if not dumped or not dump_file.exists():
                raise self.error(f"Database {self._database.name!r} could not be restored")

            self.odev.run_command(
                "restore",
                dump_file.as_posix(),
                database=LocalDatabase(self.args.name or self._database.name),
            )

    def get_dump_filename_kwargs(self) -> MutableMapping[str, Any]:
        """Return the keyword arguments to pass to Database.get_dump_filename()."""
        return {
            "filestore": self.args.filestore,
            "suffix": self._database.platform.name,
            "extension": "zip",
        }
