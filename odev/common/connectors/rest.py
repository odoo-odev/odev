"""Interact with remote endpoints using REST."""

import json
import platform
import re
from abc import ABC, abstractmethod, abstractproperty
from contextlib import contextmanager
from pathlib import Path
from types import FrameType
from typing import (
    Any,
    ClassVar,
    List,
    Literal,
    MutableMapping,
    Optional,
    Sequence,
    Union,
)
from urllib.parse import ParseResult, quote, urlparse

from requests import Response, Session
from requests.exceptions import ConnectionError as RequestsConnectionError

from odev._version import __version__
from odev.common.connectors.base import Connector
from odev.common.console import console
from odev.common.errors import ConnectorError
from odev.common.logging import LOG_LEVEL, logging
from odev.common.progress import Progress
from odev.common.signal_handling import capture_signals


ODOO_DOMAINS: List[str] = ["accounts.odoo.com", "www.odoo.sh", "odoo.com"]
"""The domains to use for storing Odoo session cookies in the secrets vault."""

ODOO_SESSION_COOKIES: List[str] = ["session_id", "td_id"]
"""The names of the Odoo session cookies."""


logger = logging.getLogger(__name__)


class RestConnector(Connector, ABC):
    """Abstract class for connecting to a remote HTTP endpoint using REST."""

    _connection: Optional[Session] = None
    """The session used to connect to the endpoint."""

    _cache: ClassVar[MutableMapping[str, Any]] = {}
    """Cache for storing the results of HTTP requests against the endpoints."""

    def __init__(self, url: str):
        """Initialize the connector.

        :param url: The URL of the endpoint.
        """
        super().__init__()

        self._url: str = url
        """The URL of the endpoint, not sanitized."""

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
            raise ConnectorError(f"Invalid URL {self._url}", self)

        return f"{self.parsed_url.scheme}://{self.parsed_url.netloc}"

    @property
    def user_agent(self) -> str:
        """Build and return a credible User-Agent string to use in HTTP requests."""
        python = f"{platform.python_implementation()} {platform.python_version()}"
        system = f"{platform.system()} {platform.release()}"
        return f"Odev/{__version__} ({python}; {system})"

    @property
    def user_agent_totp(self) -> str:
        """Build and return a credible User-Agent string to use in HTTP requests
        but spoof an existing browser implementation as Odoo Oauth crashes
        on unknown browsers and platforms during device registration.
        """
        return (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/112.0.0.0 Safari/537.36; {self.user_agent} (TOTP)"
        )

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

        for domain in {*ODOO_DOMAINS, self.parsed_url.netloc}:
            for key in ODOO_SESSION_COOKIES:
                cookie = self.store.secrets.get(
                    f"{domain}:{key}",
                    fields=("password",),
                    ask_missing=False,
                ).password

                if cookie:
                    logger.debug(f"Setting cookie {key!r} for domain {domain!r}")
                    self._connection.cookies.set(key, cookie, domain=domain)

    def disconnect(self):
        """Disconnect from the endpoint and invalidate the current session."""
        if self._connection is not None:
            self.store.secrets.set(
                f"{self.parsed_url.netloc}:cookie",
                "",
                self._connection.cookies.get("session_id", domain=self.parsed_url.netloc),
            )

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
        raise_for_status: bool = True,
        retry_on_error: bool = True,
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

        parsed = urlparse(path)

        if parsed.scheme and parsed.netloc:
            url = path
        else:
            if not path.startswith("/"):
                path = f"/{path}"

            url = self.url + path

        kwargs.setdefault("allow_redirects", True)
        params = kwargs.pop("params", {})
        obfuscate_params = obfuscate_params or []
        obfuscated = {k: "xxxxx" for k in obfuscate_params if k in params}

        cache_key = f"{method}:{url}:{json.dumps(obfuscated, sort_keys=True)}"
        cached = self.cache(cache_key)

        if cached is not None:
            return cached

        logger_message = f"{method} {url}"

        if method == "GET" and params:
            logger_message += (
                f"?{'&'.join(f'{key}={quote(str(value))}' for key, value in {**params, **obfuscated}.items())}"
            )
            params = {"params": params}
        elif method == "POST" and params and "json" not in kwargs:
            params = {"json": {"params": params}}

        logger.debug(logger_message)

        if not self._connection.headers["User-Agent"]:
            self._connection.headers.update({"User-Agent": self.user_agent})

        try:
            response = self._connection.request(method, url, **params, **kwargs)
        except RequestsConnectionError as error:
            if retry_on_error:
                logger.debug(error)
                return self._request(
                    method,
                    path,
                    obfuscate_params=obfuscate_params,
                    raise_for_status=raise_for_status,
                    retry_on_error=False,
                    **kwargs,
                )

            raise ConnectorError(f"Could not connect to {self.name}", self) from error

        if raise_for_status:
            response.raise_for_status()

        console.clear_line(int(LOG_LEVEL == "DEBUG"))
        logger.debug(
            logger_message
            + f" -> [{response.status_code}] {response.reason} ({response.elapsed.total_seconds():.3f} seconds)"
        )

        self.cache(cache_key, response)

        for cookie in self._connection.cookies:
            if cookie.name in ODOO_SESSION_COOKIES:
                logger.debug(f"Storing cookie {cookie.name!r} for domain {cookie.domain!r}")
                self.store.secrets.set(
                    f"{cookie.domain}:{cookie.name}",
                    "",
                    cookie.value,
                )

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

    def download(self, path: str, file_path: Path, progress_message: str = "Downloading", **kwargs) -> Path:
        """Download a file from the endpoint.
        :param path: The path to the resource.
        :param filename: The name of the file to save.
        :param progress_message: The message to display in the progress bar.
        :param kwargs: Additional keyword arguments to pass to the request.
        :return: The response from the endpoint.
        :rtype: requests.Response
        """
        progress = Progress(download=True)
        task = progress.add_task(progress_message, total=None)

        def signal_handler_progress(signal_number: int, frame: Optional[FrameType] = None, message: str = None):
            progress.stop_task(task)
            progress.stop()
            logger.warning(f"{progress._tasks.get(task).description}: task interrupted by user")
            raise KeyboardInterrupt

        try:
            with capture_signals(handler=signal_handler_progress), self.get(path, **kwargs, stream=True) as response:
                progress.start()
                content_length = int(response.headers.get("content-length", 0))
                progress.update(task, total=content_length)
                progress.start_task(task)

                with file_path.open("wb") as file:
                    for chunk in response.iter_content(chunk_size=1024):
                        file.write(chunk)
                        progress.advance(task, advance=len(chunk))
        except Exception as exception:
            progress.stop_task(task)
            progress.stop()
            raise exception

        progress.stop_task(task)
        progress.stop()
        return file_path
