from time import sleep

from rich.console import Group

from odev.common import progress
from odev.common.commands import PaasDatabaseCommand
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class RebuildCommand(PaasDatabaseCommand):
    """Rebuild an Odoo SH (PaaS) database."""

    name = "rebuild"

    arguments = [
        {
            "name": "wait",
            "aliases": ["--no-wait"],
            "action": "store_false",
            "help": "Do not wait for the rebuild to complete.",
        },
    ]

    def run(self):
        build_id: int = self.database.build.id

        with progress.spinner(f"Rebuilding database {self.database.build.name!r}"):
            self.database.rebuild()

        if not self.args.wait:
            return logger.info(f"Started rebuilding {self.database.name!r}")

        spinner_message: str = "Waiting for new build to start"

        with progress.spinner(spinner_message) as spinner:
            last_build = self.database.build

            while last_build.id == build_id:
                sleep(1)

                with self.database.paas.nocache():
                    last_build = self.database.builds_for_branch()[0]
                    logger.debug(f"Current build id: {build_id}")
                    logger.debug(f"Last build id:    {last_build.id}")

            with self.database.paas.nocache():
                del self.database._build
                del self.database._build_info
                self.database.name = last_build.name
                spinner_message = f"Waiting for build {self.database.build.name!r} to complete"

            for build in self.database.await_build():
                group = Group(self.console.render_str(spinner_message), self.database.build_panel(build=build))

                spinner.update(status=group)

        self.print(self.database.build_panel(build=build))
