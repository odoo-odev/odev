"""Connect to Odoo SaaS databases."""

import json
import re
from functools import lru_cache
from typing import (
    Any,
    ClassVar,
    Literal,
    MutableMapping,
    Optional,
    Union,
)
from urllib.parse import ParseResult, urlparse

from requests import Response, Session

from odev.common import prompt
from odev.common.connectors.base import Connector
from odev.common.logging import LOG_LEVEL, logging


logger = logging.getLogger(__name__)


class SaasConnector(Connector):
    """Class for connecting to a SaaS database support backend."""

    _connection: Optional[Session] = None
    """The session used to connect to the SaaS backend."""

    _url: str = None
    """The URL of the SaaS database, not sanitized."""

    _cache: ClassVar[MutableMapping[str, Any]] = {}
    """Cache for storing the results of HTTP requests against the SaaS databases."""

    def __init__(self, url: str):
        """Initialize the connector.

        :param url: The URL of the SaaS database.
        """
        super().__init__()

        self._url: str = url
        """The URL of the SaaS database."""

    @property
    def parsed_url(self) -> ParseResult:
        """Return the parsed URL of the SaaS database."""
        url = self._url

        if not re.match(r"https?://", url):
            url = f"https://{url}"

        return urlparse(url)

    @property
    def url(self) -> str:
        """Return the sanitized URL to the SaaS database."""
        if not self.parsed_url.netloc:
            raise ValueError(f"Invalid URL {self._url}")

        return f"{self.parsed_url.scheme}://{self.parsed_url.netloc}"

    @property
    def name(self) -> str:
        """Return the name of the SaaS database."""
        return self.parsed_url.netloc.removesuffix(".odoo.com")

    @property
    def login(self) -> str:
        """Login for odoo.com."""
        return self.store.secrets.get("odoo.com", fields=["login"], prompt_format="Odoo account {field}:").login

    @property
    def password(self):
        """Password or API key for odoo.com."""
        return self.store.secrets.get("odoo.com", fields=["password"], prompt_format="Odoo API key:").password

    def connect(self):
        """Login to the support page of the Odoo SaaS database."""
        if self._connection is not None:
            return

        self._connection = Session()

    def disconnect(self):
        """Disconnect from the SaaS database support page and invalidate the current session."""
        if self._connection is not None:
            self._connection.close()
            del self._connection

    def dump_path(self, include_filestore: bool = False) -> str:
        """Return the path to the dump of the SaaS database."""
        return f"saas_worker/dump.{'zip' if include_filestore else 'sql.gz'}"

    def request(
        self,
        method: Union[Literal["GET"], Literal["POST"]],
        path: str,
        authenticate: bool = True,
        params: dict = None,
        **kwargs,
    ) -> Response:
        """Executes an HTTP request to the SaaS database support page.
        Authentication is handled automatically using the Odoo credentials stored in the secrets vault.
        :param method: The HTTP method to use.
        :param path: The path to the resource.
        :param params: The parameters to pass to the request.
        :param kwargs: Additional keyword arguments to pass to the request.
        :return: The response from the SaaS database support page.
        :rtype: requests.Response
        """
        if not self.connected:
            self.connect()

        if not path.startswith("/"):
            path = f"/{path}"

        params = params or {}
        support_pass_key: str = "support-pass"

        if authenticate:
            params = {
                "support-login": self.login,
                support_pass_key: self.password,
                **params,
            }

        cache_key = f"{method}:{self.url + path}:{json.dumps(params, sort_keys=True)}"

        if cache_key in SaasConnector._cache:
            return SaasConnector._cache[cache_key]

        logger_message = f"{method} {self.url}{path}"

        if method == "GET" and params:
            masked_params = {**params, support_pass_key: "@@@@@"}
            logger_message += f"?{'&'.join(f'{key}={value}' for key, value in masked_params.items())}"
            params = {"params": params}
        elif method == "POST" and params:
            params = {"json": {"params": params}}

        logger.debug(logger_message)

        response = self._connection.request(method, self.url + path, **params, **kwargs)
        response.raise_for_status()

        prompt.clear_line(int(LOG_LEVEL == "DEBUG"))
        logger.debug(
            logger_message
            + f" -> [{response.status_code}] {response.reason} ({response.elapsed.total_seconds():.3f} seconds)"
        )

        SaasConnector._cache[cache_key] = response
        return response

    def get(self, path: str, params: dict = None, authenticate: bool = True, **kwargs) -> Response:
        """Perform a GET request to the SaaS database support page.
        Authentication is handled automatically using the Odoo credentials stored in the secrets vault.

        :param path: The path to the resource.
        :param params: The parameters to pass to the request.
        :param kwargs: Additional keyword arguments to pass to the request.
        :return: The response from the SaaS database support page.
        :rtype: requests.Response
        """
        return self.request("GET", path, params=params, authenticate=authenticate, **kwargs)

    def post(self, path: str, params: dict = None, authenticate: bool = True, **kwargs) -> Response:
        """Perform a POST request to the SaaS database support page.
        Authentication is handled automatically using the Odoo credentials stored in the secrets vault.

        :param path: The path to the resource.
        :param params: The parameters to pass to the request.
        :param kwargs: Additional keyword arguments to pass to the request.
        :return: The response from the SaaS database support page.
        :rtype: requests.Response
        """
        return self.request("POST", path, params=params, authenticate=authenticate, **kwargs)

    @property
    def exists(self) -> bool:
        """Return whether the SaaS database exists."""
        response = self.get("saas_worker/noop", allow_redirects=False, authenticate=False)
        return response.status_code == 200

    @lru_cache
    def database_info(self) -> dict:
        """Return the information about the SaaS database."""
        response = self.post("saas_worker/db_info", allow_redirects=False)
        return response.json().get("result", {})
