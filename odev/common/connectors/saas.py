"""Connect to Odoo SaaS databases."""

from functools import lru_cache
from pathlib import Path
from types import FrameType
from typing import Literal, Optional, Union

from requests import Response

from odev.common import prompt
from odev.common.connectors.rest import RestConnector
from odev.common.logging import logging
from odev.common.progress import Progress
from odev.common.signal_handling import capture_signals


logger = logging.getLogger(__name__)


class SaasConnector(RestConnector):
    """Class for connecting to a SaaS database support backend."""

    @property
    def name(self) -> str:
        """Return the name of the SaaS database."""
        return self.parsed_url.netloc.removesuffix(".odoo.com")

    @property
    def login(self) -> str:
        """Login for odoo.com."""
        return self.store.secrets.get("odoo.com:pass", fields=["login"], prompt_format="Odoo {field}:").login

    @property
    def password(self):
        """API key for odoo.com."""
        return self.store.secrets.get("odoo.com:api", fields=["password"], prompt_format="Odoo API key:").password

    def dump_path(self, include_filestore: bool = False) -> str:
        """Return the path to the dump of the SaaS database."""
        return f"saas_worker/dump.{'zip' if include_filestore else 'dump'}"

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
        params = params or {}
        support_pass_key: str = "support-pass"

        if authenticate:
            params = {
                "support-login": self.login,
                support_pass_key: self.password,
                **params,
            }

        return self._request(method, path, obfuscate_params=[support_pass_key], params=params, **kwargs)

    def dump(self, path: Path, include_filestore: bool = False) -> Path:
        """Dump the SaaS database to the specified path.
        :param path: The path to the dump file. Assumed to be a valid file location.
            If existing, the file will be overwritten.
        :param include_filestore: Whether to include the filestore in the dump.
        """
        dump_path = self.dump_path(include_filestore)
        progress = Progress()
        task = progress.add_task(
            f"Dumping database [repr.url]{self.url}[/repr.url] {'with' if include_filestore else 'without'} filestore",
            total=None,
        )

        def signal_handler_progress(signal_number: int, frame: Optional[FrameType] = None, message: str = None):
            progress.stop_task(task)
            progress.stop()
            logger.warning(f"{progress._tasks.get(task).description}: task interrupted by user")
            raise KeyboardInterrupt

        progress.start()

        with capture_signals(handler=signal_handler_progress), self.get(dump_path, stream=True) as response:
            content_length = int(response.headers.get("content-length", 0))
            progress.update(task, total=content_length)
            progress.start_task(task)

            with path.open("wb") as dump_file:
                for chunk in response.iter_content(chunk_size=1024):
                    dump_file.write(chunk)
                    progress.advance(task, advance=len(chunk))

        progress.stop_task(task)
        progress.stop()
        prompt.clear_line()
        return path

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
