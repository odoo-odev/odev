from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock

from odev.commands.database.quickstart import QuickStartCommand
from odev.common.databases import LocalDatabase, Repository

from tests.fixtures import OdevTestCase


class TestQuickStartLinksRepository(OdevTestCase):
    """The repository must be linked before the dump is restored, and still be linked afterwards."""

    def make_command(self, repository: Repository | None) -> QuickStartCommand:
        command = QuickStartCommand.__new__(QuickStartCommand)
        command._framework = self.odev
        command.args = Namespace(branch=None, version=None, name="quickstart-target", filestore=False)

        source = MagicMock()
        source.name = "quickstart-source"
        source.repository = repository
        source.platform.name = "remote"
        source._get_dump_filename.return_value = "dump.zip"
        command._database = source
        return command

    def make_dump_file(self) -> Path:
        dump_file = self.run_path / "dump.zip"
        dump_file.parent.mkdir(parents=True, exist_ok=True)
        dump_file.touch()
        return dump_file

    def test_repository_is_linked_before_restore(self):
        """Regression for #98: neutralization runs from within `restore`, so a repository linked
        only after the restore call is invisible to it.
        """
        repository = Repository("psbe-project", "odoo-ps")
        command = self.make_command(repository)
        target = MagicMock(spec=LocalDatabase)
        target.repository = None
        seen: list[Repository | None] = []

        def fake_run_command(name, *_args, database=None, **_kwargs):
            if name == "restore":
                seen.append(database.repository)
            return True

        dump_file = self.make_dump_file()

        with (
            self.patch(self.odev, "run_command", side_effect=fake_run_command),
            self.patch_property(type(self.odev), "dumps_path", dump_file.parent),
            self.patch("odev.commands.database.quickstart", "LocalDatabase", return_value=target),
        ):
            command.run()

        self.assertEqual(seen, [Repository("psbe-project", "odoo-ps")])

    def test_repository_is_still_linked_after_restore(self):
        """`restore` drops and recreates the database, which clears its entry in the data store."""
        repository = Repository("psbe-project", "odoo-ps")
        command = self.make_command(repository)
        target = MagicMock(spec=LocalDatabase)
        target.repository = None

        def fake_run_command(name, *_args, database=None, **_kwargs):
            if name == "restore":
                database.repository = None  # `restore` wipes the store entry
            return True

        dump_file = self.make_dump_file()

        with (
            self.patch(self.odev, "run_command", side_effect=fake_run_command),
            self.patch_property(type(self.odev), "dumps_path", dump_file.parent),
            self.patch("odev.commands.database.quickstart", "LocalDatabase", return_value=target),
        ):
            command.run()

        self.assertEqual(target.repository, Repository("psbe-project", "odoo-ps"))

    def test_no_repository_on_source_links_nothing(self):
        command = self.make_command(None)
        target = MagicMock(spec=LocalDatabase)
        target.repository = None

        dump_file = self.make_dump_file()

        with (
            self.patch(self.odev, "run_command", return_value=True),
            self.patch_property(type(self.odev), "dumps_path", dump_file.parent),
            self.patch("odev.commands.database.quickstart", "LocalDatabase", return_value=target),
        ):
            command.run()

        self.assertIsNone(target.repository)
