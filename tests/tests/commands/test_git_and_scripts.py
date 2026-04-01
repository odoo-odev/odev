from argparse import Namespace

from odev.commands.scripts.assets import PathfinderCommand as AssetsCommand
from odev.commands.scripts.pathfinder import PathfinderCommand
from odev.common.connectors.git import GitConnector

from tests.fixtures import OdevCommandTestCase, OdevTestCase


class TestGitCommands(OdevCommandTestCase):
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
