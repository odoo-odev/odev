from tests.fixtures import OdevTestCase


class TestDataStore(OdevTestCase):
    def test_store_exposes_table_helpers(self):
        self.assertEqual(self.odev.store.databases.name, "databases")
        self.assertEqual(self.odev.store.history.name, "history")
        self.assertEqual(self.odev.store.secrets.name, "secrets")
