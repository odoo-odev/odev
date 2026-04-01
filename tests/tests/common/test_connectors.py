from typing import cast

from requests import Session
from requests.exceptions import ConnectionError as RequestsConnectionError

from odev.common.connectors.postgres import Cursor, PostgresConnector
from odev.common.connectors.rest import RestConnector

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
