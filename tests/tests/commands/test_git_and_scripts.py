import os
from argparse import Namespace
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from git import Repo

from odev.commands.git.pull import PullCommand
from odev.commands.scripts.assets import AssetsCommand
from odev.commands.scripts.pathfinder import PathfinderCommand
from odev.common.connectors.git import GitConnector
from odev.common.mixins import ListLocalDatabasesMixin
from odev.common.string import suid
from odev.scripts.assets import regenerate_assets

from tests.fixtures import OdevCommandTestCase, OdevTestCase


class TestGitCommands(OdevCommandTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._patch_object(GitConnector, [("fetch", None), ("prune_worktrees", None), ("_check_repository", None)])

    def test_01_clone_requires_target(self):
        _, stderr = self.dispatch_command("clone")
        self.assertIn("You must specify a database or repository to clone", stderr)

    def test_02_fetch_missing_worktree(self):
        with self.patch(GitConnector, "fetch", return_value=None):
            _, stderr = self.dispatch_command("fetch", "--worktree", "missing")
        self.assertIn("does not exist", stderr)

    def test_03_pull_missing_worktree(self):
        with self.patch(GitConnector, "fetch", return_value=None):
            _, stderr = self.dispatch_command("pull", "--worktree", "missing")
        self.assertIn("does not exist", stderr)

    def test_04_worktree_name_required_for_create(self):
        _, stderr = self.dispatch_command("worktree", "--create")
        self.assertIn("provide a name for the worktree", stderr)

    def test_05_pull_output_ends_with_blank_line(self):
        """`FetchCommand.run` clears the line trailing the last worktree, so `run_hook` must end on a blank one."""
        worktree = MagicMock(name="17.0", detached=False, branch="17.0")
        worktree.name = "17.0"
        worktree.connector.name = "odoo/odoo"

        command = PullCommand.__new__(PullCommand)
        printed: list[str] = []
        titled: list[str] = []

        with (
            self.patch_property(PullCommand, "worktrees", [worktree]),
            self.patch(
                self.odev.console, "print", side_effect=lambda renderable="", *_, **__: printed.append(renderable)
            ),
            self.patch(self.odev.console, "title_rule", side_effect=titled.append),
        ):
            command.run_hook("17.0", [("odoo/odoo", 0, 0)])

        self.assertEqual(titled, ["17.0"])
        self.assertEqual(printed, [""])


class TestRepositoriesCommand(OdevCommandTestCase):
    def setUp(self):
        super().setUp()
        self.odev.config.paths.repositories = self.run_path / suid() / "repositories"

    def test_01_list_status(self):
        """Run the command, list the repositories with their branch, changes, remote status and linked databases."""
        origin = self.__repository("test/origin", days=10)
        clone = Repo.clone_from(origin.working_dir, self.odev.config.paths.repositories / "test/clone")
        self.__commit(clone, days=1)
        dirty = self.__repository("test/dirty", days=5)
        (Path(dirty.working_dir) / "untracked.txt").write_text("untracked")
        Repo.init(self.odev.config.paths.repositories / "test/empty")
        (self.odev.config.paths.repositories / "test/not-a-repository").mkdir()

        with (
            self.patch(self.odev.store.databases, "linked_repositories", {"test/clone": ["linked_db", "deleted_db"]}),
            self.patch(ListLocalDatabasesMixin, "list_databases", ["linked_db"]),
        ):
            stdout, _ = self.__dispatch()

        self.assertRegex(stdout, r"test/clone\s+main\s+↑1\s+1 day ago\s+linked_db\s")
        self.assertRegex(stdout, r"test/dirty\s+main\s+1\s+no upstream\s+5 days ago")
        self.assertRegex(stdout, r"test/empty\s+<empty>")
        self.assertNotIn("deleted_db", stdout)
        self.assertNotIn("not-a-repository", stdout)
        self.assertIn("4 repositories", stdout)

    def test_02_names_only_expression(self):
        """Run the command with `--names-only` and `--expression`, print the names of the matching repositories."""
        for name in ("test/first", "test/second", "other/first"):
            self.__repository(name)

        stdout, _ = self.__dispatch("--names-only", "--expression", "first")
        self.assertIn("other/first\ntest/first\n", stdout)
        self.assertNotIn("test/second", stdout)

    def test_03_no_result(self):
        """Run the command when no repository matches, print an error message."""
        self.__repository("test/first")
        _, stderr = self.__dispatch("--expression", "missing")
        self.assertIn("No repository found", stderr)
        self.assertIn("matching pattern 'missing'", stderr)

    def test_04_sort_by_date(self):
        """Run the command sorted by date, order the repositories from the oldest to the latest commit."""
        self.__repository("test/recent", days=1)
        self.__repository("test/old", days=30)
        Repo.init(self.odev.config.paths.repositories / "test/empty")

        stdout, _ = self.__dispatch("--sort", "date")
        names = ["test/empty", "test/old", "test/recent"]
        self.assertEqual(sorted(names, key=stdout.index), names)

    def test_05_nested_repository(self):
        """Run the command with a repository cloned from another host, list it under its full name and link it."""
        self.__repository("gitlab.com/group/subgroup/project")
        Repo.init(self.odev.config.paths.repositories / "gitlab.com/group/subgroup/project/nested")

        with (
            self.patch(
                self.odev.store.databases, "linked_repositories", {"gitlab.com/group/subgroup/project": ["linked_db"]}
            ),
            self.patch(ListLocalDatabasesMixin, "list_databases", ["linked_db"]),
        ):
            stdout, _ = self.__dispatch()

        self.assertRegex(stdout, r"gitlab.com/group/subgroup/project\s+main\s.*linked_db")
        self.assertNotIn("project/nested", stdout)
        self.assertIn("1 repositories", stdout)

    def test_06_behind_and_detached(self):
        """Run the command, show the commits to pull and the commit checked out on a detached head."""
        origin = self.__repository("test/origin", days=10)
        clone = Repo.clone_from(origin.working_dir, self.odev.config.paths.repositories / "test/clone")
        self.__commit(origin, days=1)
        clone.remotes.origin.fetch()
        origin.git.checkout(origin.head.commit.hexsha)

        stdout, _ = self.__dispatch()
        self.assertRegex(stdout, r"test/clone\s+main\s+↓1\s")
        self.assertRegex(stdout, rf"test/origin\s+<detached> {origin.head.commit.hexsha[:8]}\s")

    def __dispatch(self, *arguments: str) -> tuple[str, str]:
        """Run the command on a wide terminal so table columns are not cropped."""
        with patch.dict(os.environ, {"COLUMNS": "200"}):
            return self.dispatch_command("repos", *arguments)

    def __repository(self, name: str, days: int = 1) -> Repo:
        """Create a git repository under the repositories path with a single commit."""
        repository = Repo.init(self.odev.config.paths.repositories / name, initial_branch="main")
        self.__commit(repository, days)
        return repository

    def __commit(self, repository: Repo, days: int):
        """Commit a new file in a repository, dated some days ago."""
        path = Path(repository.working_dir) / f"file_{len(list(Path(repository.working_dir).iterdir()))}.txt"
        path.write_text(name := path.name)
        repository.index.add([name])
        date = datetime.now().astimezone() - timedelta(days=days, minutes=1)
        repository.index.commit(f"Add {name}", author_date=date, commit_date=date)


class TestScriptCommands(OdevTestCase):
    def test_01_assets_script_run_after(self):
        command = AssetsCommand.__new__(AssetsCommand)
        self.assertEqual(command.script_run_after, "regenerate_assets(env)")

    def test_02_pathfinder_formats_output(self):
        command = PathfinderCommand.__new__(PathfinderCommand)
        command.args = Namespace(origin="res.partner", destination="sale.order")
        command._framework = self.odev
        table_calls = []
        command.table = lambda headers, rows, title=None: table_calls.append((headers, rows, title))

        with self.patch(self.odev.console, "clear_line"):
            command.run_script_handle_result("[[('res.partner','partner','many2one'),('sale.order','order','')]]")

        self.assertEqual(len(table_calls), 1)
        self.assertIn("partner.order", table_calls[0][2])

    def test_03_regenerate_assets_script(self):
        env = MagicMock()
        # Mock env.cr.fetchone to return [True] (table exists)
        env.cr.fetchone.return_value = [True]

        # Mock search to return a mock list of attachments
        mock_attachment = MagicMock()
        env["ir.attachment"].search.return_value = mock_attachment
        mock_attachment.__len__.return_value = 5

        result = regenerate_assets(env)

        # Assert calls
        # 1. table check query
        env.cr.execute.assert_any_call(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'ir_asset')"
        )
        # 2. DELETE query because table exists
        env.cr.execute.assert_any_call("DELETE FROM ir_asset WHERE path LIKE '%_custom/%'")

        # 3. search call
        env["ir.attachment"].search.assert_called_once_with(
            [
                "&",
                ("res_model", "=", "ir.ui.view"),
                "|",
                ("name", "=like", "%.assets_%.css"),
                ("name", "=like", "%.assets_%.js"),
            ]
        )
        # 4. unlink
        mock_attachment.unlink.assert_called_once()
        # 5. commit
        env.cr.commit.assert_called_once()
        # 6. result
        self.assertEqual(result, "Deleted 5 assets files")

    def test_04_regenerate_assets_script_no_table(self):
        env = MagicMock()
        # Mock env.cr.fetchone to return [False] (table doesn't exist)
        env.cr.fetchone.return_value = [False]

        mock_attachment = MagicMock()
        env["ir.attachment"].search.return_value = mock_attachment
        mock_attachment.__len__.return_value = 3

        result = regenerate_assets(env)

        # Assert calls
        env.cr.execute.assert_called_once_with(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'ir_asset')"
        )
        env["ir.attachment"].search.assert_called_once()
        mock_attachment.unlink.assert_called_once()
        env.cr.commit.assert_called_once()
        self.assertEqual(result, "Deleted 3 assets files")
