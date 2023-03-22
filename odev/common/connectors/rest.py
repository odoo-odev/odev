"""Interact with remote endpoints using REST."""

import json
import platform
import re
from abc import ABC, abstractmethod, abstractproperty
from contextlib import contextmanager
from typing import (
    Any,
    ClassVar,
    Literal,
    MutableMapping,
    Optional,
    Sequence,
    Union,
)
from urllib.parse import ParseResult, urlparse

from requests import Response, Session

from odev._version import __version__
from odev.common.connectors.base import Connector
from odev.common.console import console
from odev.common.logging import LOG_LEVEL, logging


logger = logging.getLogger(__name__)


class RestConnector(Connector, ABC):
    """Abstract class for connecting to a remote HTTP endpoint using REST."""

    _connection: Optional[Session] = None
    """The session used to connect to the endpoint."""

    _url: str = None
    """The URL of the endpoint, not sanitized."""

    _cache: ClassVar[MutableMapping[str, Any]] = {}
    """Cache for storing the results of HTTP requests against the endpoints."""

    def __init__(self, url: str):
        """Initialize the connector.

        :param url: The URL of the endpoint.
        """
        super().__init__()
        self._url: str = url

    @property
    def parsed_url(self) -> ParseResult:
        """Return the parsed URL of the endpoint."""
        url = self._url

        if not re.match(r"https?://", url):
            url = f"https://{url}"

        return urlparse(url)

    @property
    def url(self) -> str:
        """Return the sanitized URL to the endpoint."""
        if not self.parsed_url.netloc:
            raise ValueError(f"Invalid URL {self._url}")

        return f"{self.parsed_url.scheme}://{self.parsed_url.netloc}"

    @property
    def user_agent(self) -> str:
        """Build and return a credible User-Agent string to use in HTTP requests."""
        python = f"{platform.python_implementation()} {platform.python_version()}"
        system = f"{platform.system()} {platform.release()}"
        return f"Odev/{__version__} ({python}; {system})"

    @property
    def name(self) -> str:
        """Return the name of the endpoint."""
        return self.parsed_url.netloc.split(".", 1)[0]

    @abstractproperty
    def exists(self) -> bool:
        """Return whether the endpoint exists."""

    @abstractproperty
    def login(self) -> str:
        """Login for authenticating to the endpoint."""

    @abstractproperty
    def password(self):
        """Password or API key for authenticating to the endpoint."""

    def connect(self):
        """Open a session to the endpoint."""
        if self._connection is not None:
            return

        self._connection = Session()

    def disconnect(self):
        """Disconnect from the endpoint and invalidate the current session."""
        if self._connection is not None:
            self._connection.close()
            del self._connection

    def cache(self, key: str, value: Response = None) -> Optional[Response]:
        """Get the cached value for the specified key.
        If value is not `None`, add the value to the cache.
        :param key: The key to get or set.
        :param value: The value to set.
        :return: The cached value.
        """
        if value is not None:
            self.__class__._cache[key] = value

        return self.__class__._cache.get(key)

    @contextmanager
    def nocache(self):
        """Context manager to disable caching of HTTP requests."""
        cache = self.__class__._cache
        self.__class__._cache = {}
        yield
        self.__class__._cache = cache

    def _request(
        self,
        method: Union[Literal["GET"], Literal["POST"]],
        path: str,
        obfuscate_params: Sequence[str] = None,
        **kwargs,
    ) -> Response:
        """Low-level execution of an HTTP request to the endpoint to enable caching and logging.
        :param method: The HTTP method to use.
        :param path: The path to the resource.
        :param obfuscate_params: The parameters to obfuscate,
            can be used to hide passwords and other sensitive information for log messages
            and cached requests.
        :param kwargs: Additional keyword arguments to pass to the request.
        :return: The response from the REST endpoint.
        :rtype: requests.Response
        """
        if not self.connected:
            self.connect()

        if not path.startswith("/"):
            path = f"/{path}"

        params = kwargs.pop("params", {})
        obfuscate_params = obfuscate_params or []
        obfuscated = {k: "xxxxx" for k in obfuscate_params if k in params}

        cache_key = f"{method}:{self.url + path}:{json.dumps(obfuscated, sort_keys=True)}"
        cached = self.cache(cache_key)

        if cached is not None:
            return cached

        logger_message = f"{method} {self.url}{path}"

        if method == "GET" and params:
            logger_message += f"?{'&'.join(f'{key}={value}' for key, value in obfuscated.items())}"
            params = {"params": params}
        elif method == "POST" and params and "json" not in kwargs:
            params = {"json": {"params": params}}

        logger.debug(logger_message)

        self._connection.headers.update({"User-Agent": self.user_agent})
        response = self._connection.request(method, self.url + path, **params, **kwargs)
        response.raise_for_status()

        console.clear_line(int(LOG_LEVEL == "DEBUG"))
        logger.debug(
            logger_message
            + f" -> [{response.status_code}] {response.reason} ({response.elapsed.total_seconds():.3f} seconds)"
        )

        self.cache(cache_key, response)
        return response

    @abstractmethod
    def request(
        self,
        method: Union[Literal["GET"], Literal["POST"]],
        path: str,
        authenticate: bool = True,
        params: dict = None,
        **kwargs,
    ) -> Response:
        """Executes an HTTP request to the endpoint.
        Authentication is handled automatically using the credentials stored in the secrets vault
        (see properties `login` and `password`).
        :param method: The HTTP method to use.
        :param path: The path to the resource.
        :param params: The parameters to pass to the request.
        :param kwargs: Additional keyword arguments to pass to the request.
        :return: The response from the endpoint.
        :rtype: requests.Response
        """

    def get(self, path: str, params: dict = None, authenticate: bool = True, **kwargs) -> Response:
        """Perform a GET request to the endpoint.
        Authentication is handled automatically using the Odoo credentials stored in the secrets vault.

        :param path: The path to the resource.
        :param params: The parameters to pass to the request.
        :param kwargs: Additional keyword arguments to pass to the request.
        :return: The response from the endpoint.
        :rtype: requests.Response
        """
        return self.request("GET", path, params=params, authenticate=authenticate, **kwargs)

    def post(self, path: str, params: dict = None, authenticate: bool = True, **kwargs) -> Response:
        """Perform a POST request to the endpoint.
        Authentication is handled automatically using the Odoo credentials stored in the secrets vault.

        :param path: The path to the resource.
        :param params: The parameters to pass to the request.
        :param kwargs: Additional keyword arguments to pass to the request.
        :return: The response from the endpoint.
        :rtype: requests.Response
        """
        return self.request("POST", path, params=params, authenticate=authenticate, **kwargs)
