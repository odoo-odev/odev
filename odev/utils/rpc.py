from typing import Optional

import odoolib


class OdooRPC:
    """
    Wrapper around OdooLib XML-RPC client.
    """

    connection: Optional[odoolib.Connection] = None

    def __init__(self, url: str, database: str, username: Optional[str] = "admin", password: Optional[str] = "admin"):
        self.url = url
        self.database = database
        self.username = username
        self.password = password

    def __enter__(self, *args, **kwargs):
        self.connection = odoolib.get_connection(
            hostname=self.url,
            database=self.database,
            login=self.username,
            password=self.password,
            protocol="jsonrpcs",
            port=443,
        )

        return self.connection

    def __exit__(self, *args, **kwargs):
        self.connection = None
