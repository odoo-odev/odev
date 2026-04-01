from unittest.mock import MagicMock

from odev.common.connectors.rpc import Model, RpcConnector
from odev.common.errors import ConnectorError

from tests.fixtures import OdevTestCase


def _mock_database(*, url: str = "https://example.com:8069", rpc_port: int = 8069, running: bool = True):
    db = MagicMock()
    db.name = "db1"
    db.url = url
    db.rpc_port = rpc_port
    db.running = running
    plat = MagicMock()
    plat.display = "Remote"
    plat.name = "remote"
    db.platform = plat
    return db


class TestRpcConnectorProperties(OdevTestCase):
    def test_url_host_without_explicit_port(self):
        rpc = RpcConnector(_mock_database(url="https://example.com:8069"))
        self.assertEqual(rpc.url, "example.com")

    def test_url_missing_raises(self):
        rpc = RpcConnector(_mock_database(url=""))
        with self.assertRaises(ConnectorError) as ctx:
            _ = rpc.url
        self.assertIn("URL not set", str(ctx.exception))

    def test_port_missing_raises(self):
        db = _mock_database()
        db.rpc_port = None
        rpc = RpcConnector(db)
        with self.assertRaises(ConnectorError) as ctx:
            _ = rpc.port
        self.assertIn("RPC port not set", str(ctx.exception))

    def test_protocol_jsonrpcs_on_https_port(self):
        rpc = RpcConnector(_mock_database(rpc_port=443))
        self.assertEqual(rpc.protocol, "jsonrpcs")

    def test_protocol_jsonrpc_non_https(self):
        rpc = RpcConnector(_mock_database(rpc_port=8069))
        self.assertEqual(rpc.protocol, "jsonrpc")

    def test_user_id_without_connection_raises(self):
        rpc = RpcConnector(_mock_database())
        rpc._connection = None
        with self.assertRaises(ConnectorError) as ctx:
            _ = rpc.user_id
        self.assertIn("user_id", str(ctx.exception))

    def test_disconnect_clears_connection(self):
        rpc = RpcConnector(_mock_database())
        rpc._connection = object()
        rpc.disconnect()
        self.assertIsNone(rpc._connection)


class TestRpcModel(OdevTestCase):
    def test_read_group_requires_groupby(self):
        inner = MagicMock()
        inner.model_name = "res.partner"
        odoo_conn = MagicMock()
        odoo_conn.get_model.return_value = inner
        conn = MagicMock()
        conn.connected = True
        conn._connection = odoo_conn

        model = Model(conn, "res.partner")
        with self.assertRaises(ValueError) as ctx:
            model.read_group([], fields=None, groupby=None)
        self.assertIn("groupby", str(ctx.exception))
