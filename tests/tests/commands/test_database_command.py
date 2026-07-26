"""Tests for the `odev database` command, which edits a database's parameters without starting it."""

from odev.common.databases import LocalDatabase, Repository

from tests.fixtures import OdevCommandTestCase


class TestDatabaseParametersCommand(OdevCommandTestCase):
    """`odev database` must go through the database model so that its parameters round-trip."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.database_name = f"{cls.run_name}-params"
        cls.database = LocalDatabase(cls.database_name)
        cls.database.create()

    @classmethod
    def tearDownClass(cls):
        # `OdevTestCase` registers its teardown as a class cleanup on top of unittest calling it,
        # so this runs twice; by the second time the framework the database needs is already gone.
        if cls.database is not None:
            cls.database.drop()
            cls.database = None
            super().tearDownClass()

    def setUp(self):
        super().setUp()
        self.addCleanup(self.odev.store.databases.delete, self.database)

    def stored(self):
        """Return the values saved in the data store for the database under test."""
        return self.odev.store.databases.get(self.database)

    def test_set_repository_persists_the_link(self):
        self.dispatch_command("database", self.database_name, "--set-repo", "odoo-ps/psbe-project")
        self.assertEqual(self.stored().repository, "odoo-ps/psbe-project")

    def test_set_repository_normalizes_urls(self):
        """A URL must be stored as `organization/repository`: the stored value is split on the
        first slash when read back, so storing a URL yields a nonsensical repository.
        """
        self.dispatch_command("database", self.database_name, "--set-repo", "https://github.com/odoo-ps/psbe-project")
        self.assertEqual(self.stored().repository, "odoo-ps/psbe-project")

    def test_set_repository_creates_the_row_when_missing(self):
        """The database has never been run under odev, so it has no row in the data store yet."""
        self.assertIsNone(self.stored())
        self.dispatch_command("database", self.database_name, "--set-repo", "odoo-ps/psbe-project")
        self.assertIsNotNone(self.stored())

    def test_remove_repository_clears_the_link(self):
        self.dispatch_command("database", self.database_name, "--set-repo", "odoo-ps/psbe-project")
        self.dispatch_command("database", self.database_name, "--remove-repo")
        self.assertIsNone(self.stored().repository)

    def test_set_and_remove_repository_are_exclusive(self):
        _, stderr = self.dispatch_command(
            "database", self.database_name, "--set-repo", "odoo-ps/psbe-project", "--remove-repo"
        )
        self.assertIn("cannot be used together", stderr)
        self.assertIsNone(self.stored())

    def test_relinking_clears_the_previous_branch(self):
        """The branch belongs to the repository, keeping it would attribute it to the new one."""
        self.database.repository = Repository("psbe-project", "odoo-ps")
        self.odev.store.databases.set_value(self.database, "branch", "17.0-fix")
        self.assertEqual(self.stored().branch, "17.0-fix")

        self.dispatch_command("database", self.database_name, "--set-repo", "odoo-ps/psbe-other")
        self.assertEqual(self.stored().repository, "odoo-ps/psbe-other")
        self.assertIsNone(self.stored().branch)

    def test_whitelist_and_unwhitelist(self):
        self.dispatch_command("database", self.database_name, "--set-repo", "odoo-ps/psbe-project")
        self.assertFalse(self.stored().whitelisted)

        self.dispatch_command("database", self.database_name, "--whitelist")
        self.assertTrue(self.stored().whitelisted)

        self.dispatch_command("database", self.database_name, "--no-whitelist")
        self.assertFalse(self.stored().whitelisted)

    def test_unknown_worktree_is_rejected(self):
        """Exercises `GitCommand.worktrees`, which reads an argument this command removes."""
        _, stderr = self.dispatch_command("database", self.database_name, "--set-worktree", "does-not-exist")
        self.assertIn("not found", stderr)

    def test_without_arguments_the_parameters_are_printed(self):
        self.dispatch_command("database", self.database_name, "--set-repo", "odoo-ps/psbe-project")
        stdout, _ = self.dispatch_command("database", self.database_name)
        self.assertIn("odoo-ps/psbe-project", stdout)
        self.assertIn("Whitelisted", stdout)


class TestDatabaseLinkRepository(OdevCommandTestCase):
    """`LocalDatabase.link_repository` is the shared entry point for linking a repository."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.database = LocalDatabase(f"{cls.run_name}-link")
        cls.database.create()

    @classmethod
    def tearDownClass(cls):
        # `OdevTestCase` registers its teardown as a class cleanup on top of unittest calling it,
        # so this runs twice; by the second time the framework the database needs is already gone.
        if cls.database is not None:
            cls.database.drop()
            cls.database = None
            super().tearDownClass()

    def setUp(self):
        super().setUp()
        self.addCleanup(self.odev.store.databases.delete, self.database)

    def test_accepts_a_repository_name(self):
        self.assertEqual(self.database.link_repository("odoo-ps/psbe-project"), Repository("psbe-project", "odoo-ps"))

    def test_accepts_an_ssh_url(self):
        linked = self.database.link_repository("git@github.com:odoo-ps/psbe-project.git")
        self.assertEqual(linked, Repository("psbe-project", "odoo-ps"))

    def test_accepts_a_repository_instance(self):
        linked = self.database.link_repository(Repository("psbe-project", "odoo-ps"))
        self.assertEqual(linked, Repository("psbe-project", "odoo-ps"))

    def test_none_unlinks(self):
        self.database.link_repository("odoo-ps/psbe-project")
        self.assertIsNone(self.database.link_repository(None))
