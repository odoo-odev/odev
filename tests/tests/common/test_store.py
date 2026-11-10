from odev.common.string import suid

from tests.fixtures import OdevTestCase


class TestDataStore(OdevTestCase):
    def test_store_exposes_table_helpers(self):
        self.assertEqual(self.odev.store.databases.name, "databases")
        self.assertEqual(self.odev.store.history.name, "history")
        self.assertEqual(self.odev.store.secrets.name, "secrets")

    def test_linked_repositories(self):
        """List the databases linked to each repository on a platform, sorted, ignoring unlinked ones."""
        table = self.odev.store.databases
        prefix = f"linked_{suid()}"
        rows = [
            (f"{prefix}_b", "local", f"{prefix}/repository"),
            (f"{prefix}_a", "local", f"{prefix}/repository"),
            (f"{prefix}_c", "local", None),
            (f"{prefix}_d", "saas", f"{prefix}/repository"),
        ]

        for name, platform, repository in rows:
            table.database.query(
                f"INSERT INTO {table.name} (name, platform, repository) VALUES (%s, %s, %s)",
                (name, platform, repository),
            )

        self.addCleanup(table.database.query, f"DELETE FROM {table.name} WHERE name LIKE %s", (f"{prefix}%",))

        self.assertEqual(table.linked_repositories()[f"{prefix}/repository"], [f"{prefix}_a", f"{prefix}_b"])
        self.assertEqual(table.linked_repositories("saas")[f"{prefix}/repository"], [f"{prefix}_d"])
