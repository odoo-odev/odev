from pathlib import Path
from unittest.mock import MagicMock

from git.exc import GitCommandError

from odev.common.connectors.git import GitWorktree

from tests.fixtures import OdevTestCase


WORKTREES_PATH = Path("/home/user/.local/share/odev/worktrees")
COMMIT = "0123456789abcdef0123456789abcdef01234567"


def porcelain(worktree: str, commit: str = COMMIT, *attributes: str) -> str:
    """Build an entry as emitted by `git worktree list --porcelain`.

    :param worktree: The path of the worktree.
    :param commit: The commit the worktree points to.
    :param attributes: The trailing attribute lines, such as `branch refs/heads/17.0` or `detached`.
    :return: The porcelain entry.
    :rtype: str
    """
    return "\n".join([f"worktree {worktree}", f"HEAD {commit}", *attributes]) + "\n"


class TestGitWorktreeParse(OdevTestCase):
    """`git worktree list --porcelain` entries should be parsed into worktree objects."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.connector = MagicMock()
        cls.connector.name = "odoo/odoo"
        cls.connector.odev.worktrees_path = WORKTREES_PATH

    def parse(self, *arguments: str) -> GitWorktree:
        """Parse a porcelain entry against the mocked connector."""
        return GitWorktree.parse(self.connector, porcelain(*arguments))

    def test_01_branch(self):
        """A worktree checked out on a branch should expose its path, commit and branch."""
        worktree = self.parse(f"{WORKTREES_PATH}/17.0/odoo", COMMIT, "branch refs/heads/17.0")

        self.assertEqual(worktree.path, WORKTREES_PATH / "17.0" / "odoo")
        self.assertEqual(worktree.commit, COMMIT)
        self.assertEqual(worktree.ref, "refs/heads/17.0")
        self.assertEqual(worktree.branch, "17.0")
        self.assertFalse(worktree.detached)
        self.assertFalse(worktree.bare)
        self.assertFalse(worktree.locked)
        self.assertFalse(worktree.prunable)

    def test_02_detached(self):
        """A detached worktree should be flagged as such and have no branch."""
        worktree = self.parse(f"{WORKTREES_PATH}/16.0/odoo", COMMIT, "detached")

        self.assertTrue(worktree.detached)
        self.assertIsNone(worktree.branch)
        self.assertIsNone(worktree.ref)

    def test_03_bare(self):
        """A bare repository should be flagged as such."""
        worktree = self.parse("/home/user/repositories/odoo/odoo", COMMIT, "bare")

        self.assertTrue(worktree.bare)
        self.assertFalse(worktree.detached)

    def test_04_locked_with_reason(self):
        """A locked worktree should keep the reason given to `git worktree lock`."""
        worktree = self.parse(f"{WORKTREES_PATH}/15.0/odoo", COMMIT, "branch refs/heads/15.0", "locked on a usb drive")

        self.assertTrue(worktree.locked)
        self.assertEqual(worktree.locked_reason, "on a usb drive")

    def test_05_locked_without_reason(self):
        """A worktree may be locked without an explanation."""
        worktree = self.parse(f"{WORKTREES_PATH}/15.0/odoo", COMMIT, "branch refs/heads/15.0", "locked")

        self.assertTrue(worktree.locked)
        self.assertIsNone(worktree.locked_reason)

    def test_06_prunable_with_reason(self):
        """A prunable worktree should keep the reason reported by git."""
        worktree = self.parse(
            f"{WORKTREES_PATH}/14.0/odoo",
            COMMIT,
            "branch refs/heads/14.0",
            "prunable gitdir file points to non-existent location",
        )

        self.assertTrue(worktree.prunable)
        self.assertEqual(worktree.prunable_reason, "gitdir file points to non-existent location")

    def test_07_flags_are_booleans(self):
        """Flags should be coerced to booleans, not left as the matched text."""
        worktree = self.parse(f"{WORKTREES_PATH}/16.0/odoo", COMMIT, "detached")

        for flag in (worktree.bare, worktree.detached, worktree.locked, worktree.prunable):
            self.assertIsInstance(flag, bool)


class TestGitWorktreeBranch(OdevTestCase):
    """Worktrees created by odev carry a local branch suffixed with the worktree name."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.connector = MagicMock()
        cls.connector.name = "odoo/odoo"
        cls.connector.odev.worktrees_path = WORKTREES_PATH

    def test_01_odev_suffix_is_stripped(self):
        """`GitConnector.create_worktree` names local branches `<revision>-odev-<worktree>`.

        The upstream revision is what commands display and compare, the local branch is what git needs.
        """
        worktree = GitWorktree.parse(
            self.connector,
            porcelain(f"{WORKTREES_PATH}/mydb/odoo", COMMIT, "branch refs/heads/17.0-odev-mydb"),
        )

        self.assertEqual(worktree.local_branch, "17.0-odev-mydb")
        self.assertEqual(worktree.branch, "17.0")

    def test_02_branch_without_suffix_is_kept(self):
        """A branch not created by odev should be reported unchanged."""
        worktree = GitWorktree.parse(
            self.connector,
            porcelain(f"{WORKTREES_PATH}/17.0/odoo", COMMIT, "branch refs/heads/17.0"),
        )

        self.assertEqual(worktree.local_branch, "17.0")
        self.assertEqual(worktree.branch, "17.0")

    def test_03_only_the_first_suffix_is_split(self):
        """A branch name containing the separator more than once should split on the first occurrence."""
        worktree = GitWorktree.parse(
            self.connector,
            porcelain(f"{WORKTREES_PATH}/mydb/odoo", COMMIT, "branch refs/heads/17.0-odev-my-odev-db"),
        )

        self.assertEqual(worktree.branch, "17.0")


class TestGitWorktreeIdentity(OdevTestCase):
    """Worktrees are named after their directory and identified by their path."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.connector = MagicMock()
        cls.connector.name = "odoo/odoo"
        cls.connector.odev.worktrees_path = WORKTREES_PATH

    def worktree(self, path: str, branch: str = "17.0") -> GitWorktree:
        """Build a worktree on a branch at the given path."""
        return GitWorktree.parse(self.connector, porcelain(path, COMMIT, f"branch refs/heads/{branch}"))

    def test_01_name_is_the_parent_directory(self):
        """A worktree under the odev worktrees directory is named after the directory holding it."""
        self.assertEqual(self.worktree(f"{WORKTREES_PATH}/17.0/odoo").name, "17.0")
        self.assertEqual(self.worktree(f"{WORKTREES_PATH}/mydb/enterprise").name, "mydb")

    def test_02_name_outside_worktrees_path(self):
        """A checkout managed outside of odev is reported as the master worktree."""
        self.assertEqual(self.worktree("/home/user/repositories/odoo/odoo").name, "master")

    def test_03_equality_on_path(self):
        """Two worktrees at the same path are the same worktree, whatever their revision."""
        self.assertEqual(self.worktree(f"{WORKTREES_PATH}/17.0/odoo"), self.worktree(f"{WORKTREES_PATH}/17.0/odoo"))
        self.assertNotEqual(self.worktree(f"{WORKTREES_PATH}/17.0/odoo"), self.worktree(f"{WORKTREES_PATH}/16.0/odoo"))
        self.assertNotEqual(self.worktree(f"{WORKTREES_PATH}/17.0/odoo"), f"{WORKTREES_PATH}/17.0/odoo")

    def test_04_hash_on_path(self):
        """Worktrees should deduplicate on their path when collected in a set."""
        worktrees = {
            self.worktree(f"{WORKTREES_PATH}/17.0/odoo", "17.0"),
            self.worktree(f"{WORKTREES_PATH}/17.0/odoo", "saas-17.2"),
            self.worktree(f"{WORKTREES_PATH}/16.0/odoo"),
        }

        self.assertEqual(len(worktrees), 2)

    def test_05_repr(self):
        """The representation should identify the worktree by name, repository and revision."""
        self.assertEqual(
            repr(self.worktree(f"{WORKTREES_PATH}/17.0/odoo")),
            "GitWorktree(name='17.0', repository='odoo/odoo', revision='17.0')",
        )


class TestGitWorktreePendingChanges(OdevTestCase):
    """Pending changes are counted from the revision list against the tracked upstream branch."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.connector = MagicMock()
        cls.connector.name = "odoo/odoo"
        cls.connector.odev.worktrees_path = WORKTREES_PATH

    def worktree(self, *attributes: str) -> GitWorktree:
        """Build a worktree with the given porcelain attributes."""
        return GitWorktree.parse(self.connector, porcelain(f"{WORKTREES_PATH}/17.0/odoo", COMMIT, *attributes))

    def patch_rev_list(self, result: str | Exception):
        """Patch `git.Repo` as used by `pending_changes` to return or raise on `rev_list`."""
        repository = MagicMock()

        if isinstance(result, Exception):
            repository.git.rev_list.side_effect = result
        else:
            repository.git.rev_list.return_value = result

        return self.patch("odev.common.connectors.git", "Repo", return_value=repository)

    def test_01_detached_has_no_upstream(self):
        """A detached worktree has nothing to compare against and reports no pending changes."""
        self.assertEqual(self.worktree("detached").pending_changes(), (0, 0))

    def test_02_counts_behind_and_ahead(self):
        """The counts should be read from `git rev-list --left-right --count`."""
        with self.patch_rev_list("12\t3"):
            self.assertEqual(self.worktree("branch refs/heads/17.0").pending_changes(), (12, 3))

    def test_03_up_to_date(self):
        """A worktree in sync with its upstream should report no pending changes."""
        with self.patch_rev_list("0\t0"):
            self.assertEqual(self.worktree("branch refs/heads/17.0").pending_changes(), (0, 0))

    def test_04_no_upstream_configured(self):
        """A branch without an upstream cannot be compared and reports no pending changes."""
        error = GitCommandError("rev-list", 128, b"fatal: no upstream configured for branch '17.0'")

        with self.patch_rev_list(error):
            self.assertEqual(self.worktree("branch refs/heads/17.0").pending_changes(), (0, 0))

    def test_05_head_does_not_point_to_a_branch(self):
        """A HEAD not pointing to a branch cannot be compared and reports no pending changes."""
        error = GitCommandError("rev-list", 128, b"fatal: HEAD does not point to a branch")

        with self.patch_rev_list(error):
            self.assertEqual(self.worktree("branch refs/heads/17.0").pending_changes(), (0, 0))

    def test_06_unexpected_git_error_is_raised(self):
        """Any other git failure should surface instead of being reported as no pending changes."""
        error = GitCommandError("rev-list", 128, b"fatal: bad revision")

        with self.patch_rev_list(error), self.assertRaises(GitCommandError):
            self.worktree("branch refs/heads/17.0").pending_changes()
