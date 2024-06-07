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
    Literal,
    MutableMapping,
    Optional,
    Sequence,
    Set,
    Union,
    cast,
)
from urllib.parse import ParseResult, urlencode, urlparse

from requests import Response, Session
from requests.exceptions import ConnectionError as RequestsConnectionError
from rich.progress import Task

from odev._version import __version__
from odev.common.connectors.base import Connector
from odev.common.console import console
from odev.common.errors import ConnectorError
from odev.common.logging import LOG_LEVEL, logging, silence_loggers
from odev.common.progress import Progress
from odev.common.signal_handling import capture_signals


logger = logging.getLogger(__name__)


class RestConnector(Connector, ABC):
    """Abstract class for connecting to a remote HTTP endpoint using REST."""

    _connection: Optional[Session] = None
    """The session used to connect to the endpoint."""

    _cache: ClassVar[MutableMapping[str, Any]] = {}
    """Cache for storing the results of HTTP requests against the endpoints."""

    _bypass_cache: ClassVar[bool] = False
    """Whether to bypass the cache for the current request."""

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
    def name(self) -> str:
        """Return the name of the endpoint."""
        return self.parsed_url.netloc

    @abstractproperty
    def exists(self) -> bool:
        """Return whether the endpoint exists."""
        raise NotImplementedError

    def login(self) -> str:
        """Login for authenticating to the endpoint."""
        return self.store.secrets.get(self.name, scope="user", fields=["login"]).login

    def password(self) -> str:
        """Password or API key for authenticating to the endpoint."""
        return self.store.secrets.get(self.name, scope="user", fields=["password"]).password

    @property
    def session_cookie(self) -> str:
        """Return the session cookie for the endpoint."""
        return self.store.secrets.get(
            self.parsed_url.netloc,
            scope="session_id",
            fields=["password"],
            ask_missing=False,
        ).password

    @property
    def session_domains(self) -> Set[str]:
        """Domains to store session cookies for."""
        return {
            self.parsed_url.netloc,
        }

    @property
    def session_cookies(self) -> Set[str]:
        """Session cookies to store."""
        return {
            "session_id",
        }

    def _load_cookies(self):
        """Load session cookies from the secrets vault."""
        if self._connection is None:
            return

        with silence_loggers("odev.common.store.tables.secrets"):
            for domain in self.session_domains:
                for key in self.session_cookies:
                    cookie = self.store.secrets.get(domain, fields=["password"], scope=key, ask_missing=False).password

                    if cookie:
                        self._connection.cookies.set(key, cookie, domain=domain)

    def _save_cookies(self):
        """Save session cookies to the secrets vault."""
        if self._connection is None:
            return

        for domain in self.session_domains:
            for key in self.session_cookies:
                cookie = self._connection.cookies.get(key, domain=domain)

                if cookie:
                    self.store.secrets.set(domain, "", cookie, scope=key)

    def _clear_cookies(self):
        """Clear the cookies for the given domain, recursively going up to the parent domain if no cookies exist
        for the given one.
        """
        if self._connection is None:
            return

        for domain in self.session_domains:
            for scope in self.session_cookies:
                self.store.secrets.invalidate(domain, scope=scope)

            try:
                self._connection.cookies.clear(domain=domain)
            except KeyError:
                pass

    def connect(self):
        """Open a session to the endpoint."""
        if self._connection is not None:
            return

        self._connection = Session()  # type: ignore [assignment]
        self._load_cookies()

    def disconnect(self):
        """Disconnect from the endpoint and invalidate the current session."""
        if self._connection is not None:
            self._save_cookies()
            self._connection.close()
            del self._connection

    def invalidate_session(self):
        """Clear the session cookies."""
        if self._connection is None:
            return

        logger.debug("Invalidating session cookies")
        self._clear_cookies()

    def cache(self, key: str, value: Optional[Response] = None) -> Optional[Response]:
        """Get the cached value for the specified key.
        If value is not `None`, add the value to the cache.
        :param key: The key to get or set.
        :param value: The value to set.
        :return: The cached value.
        """
        if RestConnector._bypass_cache:
            return None

        if value is not None:
            RestConnector._cache[key] = value

        return RestConnector._cache.get(key)

    @contextmanager
    def nocache(self):
        """Context manager to disable caching of HTTP requests."""
        bypass_cache = RestConnector._bypass_cache
        RestConnector._bypass_cache = True
        yield
        RestConnector._bypass_cache = bypass_cache

    def _request(
        self,
        method: Literal["GET", "POST", "HEAD"],
        path: str,
        obfuscate_params: Optional[Sequence[str]] = None,
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
        :param raise_for_status: Whether to raise an exception if the request fails.
        :param retry_on_error: Whether to retry the request if it fails.
        :param kwargs: Additional keyword arguments to pass to the request.
        :return: The response from the REST endpoint.
        :rtype: requests.Response
        """
        if not self.connected:
            self.connect()

        assert self._connection is not None, "Connection was not established"
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

        if params:
            logger_message += f"?{urlencode(params | obfuscated)}"

        if not self._connection.headers["User-Agent"]:
            self._connection.headers.update({"User-Agent": self.user_agent})

        try:
            logger.debug(logger_message)
            response = self._connection.request(method, url, params=params or None, **kwargs)
            console.clear_line(int(LOG_LEVEL == "DEBUG"))
            logger.debug(
                logger_message
                + f" -> [{response.status_code}] {response.reason} ({response.elapsed.total_seconds():.3f} seconds)"
            )
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

        self.cache(cache_key, response)
        self._save_cookies()
        return response

    @abstractmethod
    def request(
        self,
        method: Union[Literal["GET"], Literal["POST"]],
        path: str,
        authenticate: bool = True,
        params: Optional[dict] = None,
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

    def get(self, path: str, params: Optional[dict] = None, authenticate: bool = True, **kwargs) -> Response:
        """Perform a GET request to the endpoint.
        Authentication is handled automatically using the Odoo credentials stored in the secrets vault.

        :param path: The path to the resource.
        :param params: The parameters to pass to the request.
        :param kwargs: Additional keyword arguments to pass to the request.
        :return: The response from the endpoint.
        :rtype: requests.Response
        """
        return self.request("GET", path, params=params, authenticate=authenticate, **kwargs)

    def post(self, path: str, params: Optional[dict] = None, authenticate: bool = True, **kwargs) -> Response:
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

        def signal_handler_progress(
            signal_number: int, frame: Optional[FrameType] = None, message: Optional[str] = None
        ):
            progress.stop_task(task)
            progress.stop()
            logger.warning(f"{cast(Task, progress._tasks.get(task)).description}: task interrupted by user")
            raise KeyboardInterrupt

        try:
            with capture_signals(handler=signal_handler_progress), self.get(
                path, **kwargs, stream=True, authenticate=False
            ) as response:
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
