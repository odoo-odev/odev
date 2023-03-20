"""Connect to Odoo PaaS (Odoo SH) projects and databases."""

import re
from typing import (
    Any,
    List,
    Literal,
    Mapping,
    MutableMapping,
    Optional,
    Union,
)
from urllib.parse import urlparse

from parsel.selector import Selector
from requests import Response
from requests.exceptions import HTTPError

from odev.common import prompt
from odev.common.connectors.rest import RestConnector
from odev.common.logging import logging


logger = logging.getLogger(__name__)


ODOOSH_DOMAIN = "www.odoo.sh"
ODOOSH_URL_BASE = f"https://{ODOOSH_DOMAIN}/"


class PaasConnector(RestConnector):
    """Class for connecting to an Odoo SH project."""

    _repository: Optional[Mapping[str, str]] = None
    """The repository mapping of the Odoo SH project, as selected from `/support/json/repos`."""

    _user: Optional[Mapping[str, str]] = None
    """The user used for impersonation on the Odoo SH project."""

    def __init__(self, project: str):
        """Initialize the connector.
        :param project: The name or URL of the Odoo SH project.
        """
        self._name: str = project
        """The name or URL of the Odoo SH project."""

        super().__init__(ODOOSH_URL_BASE)

    @property
    def name(self) -> str:
        """Return the name of the PaaS project."""
        return self._name
        # return re.sub(r"(\.dev)?\.odoo\.com$", "", self.parsed_url.netloc)

    @property
    def login(self) -> str:
        """Login for odoo.com."""
        return self.store.secrets.get(
            "odoo.com:pass",
            fields=["login"],
            prompt_format="Odoo account {field}:",
        ).login

    @property
    def password(self) -> str:
        """Password for odoo.com."""
        return self.store.secrets.get(
            "odoo.com:pass",
            fields=["password"],
            prompt_format="Odoo account {field}:",
        ).password

    @property
    def github_login(self) -> str:
        """GitHub username."""
        return self.store.secrets.get(
            "github.com:pass",
            fields=["login"],
            prompt_format="GitHub username:",
        ).login

    @property
    def cookie(self) -> Optional[str]:
        """Session cookie for odoo.sh."""
        if not self.connected:
            return None

        return self._connection.cookies.get("session_id", None, domain=ODOOSH_DOMAIN)

    @property
    def support_path(self) -> str:
        """Return the URL to log in to Odoo SH."""
        return "/_odoo/support"

    @property
    def login_path(self) -> str:
        """Return the URL to log in to Odoo SH."""
        return "/web/login"

    @property
    def authenticated(self) -> bool:
        """Test whether the session is valid and we are signed in."""
        with self.nocache():
            return self.profile is not None

    @property
    def profile(self) -> Mapping[str, Any]:
        """Return the current user profile."""
        result = self.rpc("/project/json/user/profile")
        assert isinstance(result, dict)
        return result

    @property
    def repository(self) -> Mapping[str, Any]:
        """Return the repository for the current project."""
        if self._repository is None:
            self._repository = self.select_repository()

        return self._repository

    @property
    def user(self) -> Mapping[str, Any]:
        """Return the user for the current project."""
        if self._user is None:
            self._user = self.select_user()

        return self._user

    @property
    def exists(self) -> bool:
        """Return whether the PaaS project exists."""
        return bool(self.repository)

    def extract_form_inputs(self, response: Response) -> MutableMapping[str, str]:
        """Extract the input fields from the response's content.
        :param response: A requests.Response object to extract the fields from.
        :return: A dictionary with the input fields and their value as read from the response text.
        :rtype: dict
        """
        return {
            field.attrib.get("name"): field.attrib.get("value", "")
            for field in Selector(response.text).xpath("//form//input")
        }

    def invalidate_session(self):
        """Clear the session cookies."""
        logger.debug("Invalidating Odoo SH session cookies.")
        self._connection.cookies.clear(domain=ODOOSH_DOMAIN)

    def request(
        self,
        method: Union[Literal["GET"], Literal["POST"]],
        path: str,
        authenticate: bool = True,
        params: MutableMapping[str, Any] = None,
        **kwargs,
    ) -> Response:
        """Make a request to Odoo SH.
        :param method: The HTTP method to use.
        :param path: The path to the resource.
        :param authenticate: Whether to authenticate the request.
        :param params: The parameters to pass to the request.
        :param kwargs: Additional keyword arguments to pass to the request.
        :return: The response from Odoo SH.
        :rtype: requests.Response
        """
        params = params or {}

        if authenticate and not self.cookie:
            self._login()

        try:
            response = self._request(method, path, params=params, **kwargs)
        except HTTPError as error:
            if authenticate and self.cookie is not None:
                self.invalidate_session()
                return self.request(method, path, authenticate, params, **kwargs)

            raise error

        return response

    def _login(self):
        """Log in to odoo.sh and save the session cookie for subsequent requests
        requiring authentication.
        """
        with self.nocache():
            web_login = self.get(self.support_path, authenticate=False)

            fields = self.extract_form_inputs(web_login)
            fields.update({"login": self.login, "password": self.password})

            web_login = self.post(self.login_path, authenticate=False, data=fields)
            web_login_path: str = urlparse(web_login.url).path

            if web_login.status_code != 200 or web_login_path == self.login_path:
                logger.warning("Failed to log in to Odoo SH, please check your credentials")
                self.store.secrets.get("odoo.com:pass", prompt_format="Odoo account {field}:", force_ask=True)
                return self._login()
            elif web_login_path != self.support_path:
                # Obfuscate the password before raising because locals are
                # displayed in tracebacks
                fields.update({"password": "*****"})
                raise RuntimeError("Unexpected redirect after logging in to Odoo SH")

    def rpc(
        self,
        path: str,
        method: str = "call",
        params: MutableMapping[str, Any] = None,
        **kwargs,
    ) -> Optional[Union[Mapping[str, Any], List[Mapping[str, Any]]]]:
        """Make a JSON-RPC request to Odoo SH support backend and fetch additional
        (lazy-loaded) data.
        :param path: The path to the resource.
        :param method: The JSON-RPC method to call.
        :param params: The parameters to pass to the request.
        :param kwargs: Additional keyword arguments to pass to the request.
        :return: The result of the JSON-RPC call.
        :rtype: dict | list | None
        """
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
        }

        response = self.post(path, json=payload, **kwargs)
        result = response.json().get("result")
        error = result.get("error") if isinstance(result, dict) else response.json().get("error", {}).get("message")

        if error is not None:
            if "session expired" in error.lower():
                self.invalidate_session()
                return self.rpc(path, method, params, **kwargs)

            raise RuntimeError(result["error"])

        return result

    def list_repositories(self) -> List[Mapping[str, Any]]:
        """Return the list of repositories for the current project."""
        result = self.rpc("/support/json/repos")
        assert isinstance(result, list)
        return result

    def list_users(self) -> List[Mapping[str, Any]]:
        """Return the list of users for the current project."""
        result = self.rpc("/support/json/repo_users", params={"repository_id": self.repository["id"]})
        assert isinstance(result, list)
        return result

    def _filter_repositories(self) -> List[Mapping[str, Any]]:
        """Filter the list of repositories for the current project."""
        re_full_name = re.compile(rf"(?<=/)(?:ps\w{2}-)?{self._name}", re.IGNORECASE)
        re_project_name = re.compile(rf"(?:odoo-ps-)?(?:ps\w{2}-)?{self._name}", re.IGNORECASE)

        return [
            repo
            for repo in self.list_repositories()
            if repo["full_name"] == self._name
            or re_full_name.search(repo["full_name"])
            or re_project_name.search(repo["project_name"])
        ]

    def select_repository(self) -> Mapping[str, Any]:
        """Return the repository for the current project."""
        repositories = self._filter_repositories()

        if not repositories:
            raise ValueError(f"No repository found for project {self._name!r}")

        if len(repositories) > 1:
            selected = prompt.select(
                f"Multiple repositories found for project {self._name!r}:",
                choices=[(repo["full_name"], f"{repo['project_name']} ({repo['full_name']})") for repo in repositories],
            )

            return next(repo for repo in repositories if repo["full_name"] == selected)

        return repositories[0]

    def select_user(self) -> Mapping[str, Any]:
        """Filter the list of users for the current project.
        Select the current user if she/he is a member of the project or fallback to the first
        registered user otherwise.
        """
        user = next((user for user in self.list_users() if user["email"] == self.login), None)

        if user is None:
            user = next((user for user in self.list_users() if user["username"] == self.github_login), None)

        if user is None:
            user = self.list_users()[0]
            logger.warning(
                f"""
                GitHub user {self.github_login!r} is not a member of the {self._name!r} project, consider adding
                her/him to the list of users. Now impersonating the project owner instead: {user["username"]!r}.
                """
            )

        return user

    def _impersonate(self):
        """Impersonate the project owner to access the Odoo SH backend."""
        with self.nocache():
            odoo_support = self.get(self.support_path)

            fields = self.extract_form_inputs(odoo_support)
            fields.update(
                {
                    "repository_id": self.repository["id"],
                    "hosting_user_id": self.user["hosting_user_id"][0],
                    "repository_search": f"{self.repository['full_name']} ({self.repository['project_name']})",
                }
            )

            self.post("/support/impersonate", data=fields)

        if self.profile is None or self.profile.get("errors"):
            raise RuntimeError(
                f"Failed to impersonate {self.user['username']!r} in project {self.repository['project_name']!r}"
            )

        profile = self.profile.get("values")
        logger.debug(
            f"Impersonated {profile['username']!r} ({profile['email']!r}) "
            f"with {self.user['access_level']} access level "
            f"in project {self.repository['project_name']!r} ({self.repository['full_name']!r})"
        )
