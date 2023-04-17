from rich.console import Group

from odev.common import progress
from odev.common.commands import PaasDatabaseCommand
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class BuildCommand(PaasDatabaseCommand):
    """Monitor the last build(s) of an instance of a PaaS database."""

    name = "build"
    aliases = ["builds"]

    arguments = [
        {
            "name": "show_count",
            "aliases": ["-s", "--show"],
            "action": "store_int",
            "help": "How many builds should be shown, defaults to 1 (only the last build is shown).",
            "default": 1,
        },
        {
            "name": "wait",
            "aliases": ["--no-wait"],
            "action": "store_false",
            "help": "Do not wait for the rebuild to complete.",
        },
    ]

    _database_exists_required = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.args.show_count > 1 and not self.args.wait:
            raise self.error("Arguments --show and --no-wait cannot be used together")

    def run(self):
        if self.args.show_count > 1:
            return self.list_builds()

        if self.database.build.final:
            return self.print(self.database.build_panel())

        spinner_message: str = f"Waiting for build {self.database.build.name!r} to complete"

        with progress.spinner(spinner_message) as spinner:
            for build in self.database.await_build():
                group = Group(self.console.render_str(spinner_message), self.database.build_panel(build=build))

                spinner.update(status=group)

        self.print(self.database.build_panel(build=build))

    def list_builds(self):
        builds = self.database.builds_for_branch()[: self.args.show_count]

        if not builds:
            return self.error(f"No builds found for database {self.database.name!r}")

        for build in builds:
            self.print(self.database.build_panel(build=build))
