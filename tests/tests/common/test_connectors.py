from typing import cast

from requests import Session
from requests.exceptions import ConnectionError as RequestsConnectionError

from odev.common.connectors.postgres import Cursor, PostgresConnector
from odev.common.connectors.rest import RestConnector
from odev.common.postgres import PostgresDatabase

from tests.fixtures import OdevTestCase


class DummyResponse:
    def __init__(self, status_code: int = 200):
        self.status_code = status_code
        self.reason = "OK"
        self.elapsed = type("Elapsed", (), {"total_seconds": lambda self: 0.01})()

    def raise_for_status(self):
        return None


class DummySession:
    def __init__(self):
        self.headers = {"User-Agent": ""}
        self.cookies = type(
            "Cookies",
            (),
            {
                "set": lambda *args, **kwargs: None,
                "get": lambda *args, **kwargs: None,
                "clear": lambda *args, **kwargs: None,
            },
        )()
        self.calls = []

    def request(self, method, url, params=None, **kwargs):
        self.calls.append((method, url, params, kwargs))
        return DummyResponse()

    def close(self):
        return None


class DummyRestConnector(RestConnector):
    @property
    def exists(self) -> bool:
        return True

    def request(self, method, path, authenticate=True, params=None, **kwargs):
        return self._request(method, path, params=params, **kwargs)


class TestConnectors(OdevTestCase):
    def test_01_rest_request_sets_default_timeout(self):
        connector = DummyRestConnector("https://example.com")
        session = DummySession()
        connector._connection = cast(Session, session)

        connector._request("GET", "/health")

        _, _, _, kwargs = session.calls[-1]
        self.assertEqual(kwargs["timeout"], 30.0)

    def test_02_rest_nocache_restores_state_on_error(self):
        connector = DummyRestConnector("https://example.com")

        with self.assertRaises(RuntimeError), connector.nocache():
            raise RuntimeError("boom")

        self.assertFalse(RestConnector._bypass_cache)

    def test_03_rest_request_retries_connection_error_once(self):
        connector = DummyRestConnector("https://example.com")
        session = DummySession()

        def fail_then_succeed(*args, **kwargs):
            if len(session.calls) == 0:
                session.calls.append(("ERR", "", None, {}))
                raise RequestsConnectionError("temporary")
            return DummyResponse()

        session.request = fail_then_succeed
        connector._connection = cast(Session, session)
        response = connector._request("GET", "/ok")
        self.assertEqual(response.status_code, 200)

    def test_04_postgres_nocache_restores_state_on_error(self):
        connector = PostgresConnector("postgres")

        with self.assertRaises(RuntimeError), connector.nocache():
            raise RuntimeError("boom")

        self.assertFalse(PostgresConnector._nocache)

    def test_05_cursor_transaction_does_not_commit_on_error(self):
        class DummyCursor:
            def __init__(self):
                self.calls = []

            def execute(self, statement):
                self.calls.append(statement)

        cursor = DummyCursor()

        with self.assertRaises(RuntimeError), Cursor.transaction(cursor):  # type: ignore[arg-type]
            raise RuntimeError("boom")

        self.assertEqual(cursor.calls, ["BEGIN", "ROLLBACK"])


class TestPostgresConnectionLifecycle(OdevTestCase):
    """A block has to close the connection it opened, and nested blocks have to share one.

    `ensure_connected` wraps every method of a database in `with self:`, so anything less means a fresh
    PostgreSQL backend per call: enough of them at once and the server runs out of connection slots.
    """

    def setUp(self):
        super().setUp()
        self.database = PostgresDatabase(self.odev.name)
        """A handle on the datastore database, connected and disconnected by the tests."""

    def backends(self, name: str) -> int:
        """Count the backends PostgreSQL currently holds for a database."""
        with PostgresConnector() as psql, psql.nocache():
            result = psql.query(f"SELECT count(*) FROM pg_stat_activity WHERE datname = '{name}'")

        return result[0][0] if isinstance(result, list) else 0

    def test_01_block_closes_what_it_opened(self):
        """Leaving a block should disconnect the connector the block connected."""
        with self.database:
            self.assertTrue(self.database.connector.connected)

        self.assertFalse(self.database.connector.connected)

    def test_02_nested_blocks_share_one_connection(self):
        """An inner block should join the connection of the outer one instead of opening its own."""
        with self.database:
            connector = self.database.connector

            with self.database:
                self.assertIs(self.database.connector, connector, "the inner block should reuse the connector")

            self.assertTrue(connector.connected, "the inner block should not close what the outer one uses")

        self.assertFalse(connector.connected, "the outermost block should close it")

    def test_03_repeated_calls_do_not_pile_up_backends(self):
        """Decorated methods each open a block, and those should not accumulate connections."""
        baseline = self.backends(self.database.name)

        for _ in range(20):
            self.database.table_exists("history")

        self.assertLessEqual(
            self.backends(self.database.name),
            baseline,
            "connections opened by the calls should have been closed again",
        )

    def test_04_store_keeps_a_single_connection(self):
        """The datastore is read by every command and holds its connection rather than reopening it."""
        connector = self.odev.store.connector
        self.assertTrue(connector.connected, "the store should be connected as soon as it exists")

        backends = self.backends(self.odev.store.name)

        for _ in range(20):
            self.odev.store.table_exists("history")

        self.assertIs(self.odev.store.connector, connector, "the store should keep the same connector")
        self.assertTrue(connector.connected, "a block should not close the connection the store holds")
        self.assertEqual(self.backends(self.odev.store.name), backends, "the store should hold a single backend")
