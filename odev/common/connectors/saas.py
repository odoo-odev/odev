"""Connect to Odoo SaaS databases."""

from pathlib import Path
from typing import Literal, Union

from requests import Response

from odev.common.connectors.rest import RestConnector
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class SaasConnector(RestConnector):
    """Class for connecting to a SaaS database support backend."""

    @property
    def name(self) -> str:
        """Return the name of the SaaS database."""
        return self.parsed_url.netloc.removesuffix(".odoo.com")

    @property
    def exists(self) -> bool:
        """Return whether the SaaS database exists."""
        response = self.get("saas_worker/noop", allow_redirects=False, authenticate=False, raise_for_status=False)
        return response.status_code == 200

    @property
    def login(self) -> str:
        """Login for odoo.com."""
        return self.store.secrets.get("odoo.com:pass", fields=["login"], prompt_format="Odoo {field}:").login

    @property
    def password(self) -> str:
        """API key for odoo.com."""
        return self.store.secrets.get("odoo.com:api", fields=["password"], prompt_format="Odoo API key:").password

    @property
    def support_path(self) -> str:
        """Return the path to the SaaS database support page."""
        return "_odoo/support"

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
        progress_message = (
            f"Dumping database [repr.url]{self.url}[/repr.url] {'with' if include_filestore else 'without'} filestore"
        )
        return self.download(dump_path, path, progress_message=progress_message)

    def database_info(self) -> dict:
        """Return the information about the SaaS database."""
        response = self.post("saas_worker/db_info", allow_redirects=False)
        return response.json().get("result", {})
