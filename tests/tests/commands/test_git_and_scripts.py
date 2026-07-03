from argparse import Namespace
from unittest.mock import MagicMock

from odev.commands.scripts.assets import PathfinderCommand as AssetsCommand
from odev.commands.scripts.pathfinder import PathfinderCommand
from odev.common.connectors.git import GitConnector
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
