
import re
import requests
from bs4 import BeautifulSoup

from typing import Optional, List, MutableMapping, Any, Tuple, Mapping, Sequence

from odev.utils import logging

logger = logging.getLogger(__name__)


class SupportError(Exception):
    """Base class for Support page connexion errors"""


class SupportSessionError(SupportError):
    """Session-related support page connexion errors (es. expired cookie)"""


class SupportConnection():

    def __init__(self, login: str, passwd: str, repo_name: str, github_user: str):
        self.login: str = login
        self.passwd: str = passwd
        self.repo: str = repo_name
        self.github_user: str = github_user

        self.impersonate_page_url = "/_odoo/support"
        self.session: Optional[requests.Session] = None

        self.headers: MutableMapping[str, str] = {
                "user-agent": "odev (https://github.com/odoo-ps/psbe-ps-tech-tools/tree/odev)"
            }

    def login(self) -> None:
        self.session = requests.Session()
        resp: requests.Response

        # do login
        login_data: MutableMapping[str, str] = {
            "redirect": self.impersonate_page_url,
            "login": self.login,
            "password": self.passwd,
        }
        resp = self.session.get(
            f"https://www.odoo.sh/web/login?debug=1&redirect={self.impersonate_page_url}",
            headers=self.headers,
        )
        login_data["csrf_token"] = self.__extract_csrf_token(resp)

        resp = self.session.post(
            "https://www.odoo.sh/web/login", data=login_data, headers=self.headers
        )
        if resp.status_code != 200:
            raise SupportSessionError("Failed logging in to odoo.sh")

        return resp

    def impersonate(self, resp): 
        if self.impersonate_page_url not in resp.url:
            raise SupportError(
                f"Unexpected redirect for impersonation page, got: {resp.url}"
            )
        impersonation_csrf_token: str = self.extract_csrf_token(resp)

        # get repos and match gh user
        repos: Sequence[Mapping] = self.jsonrpc("https://www.odoo.sh/support/json/repos")
        repo: Mapping
        matching_repos: List[Mapping] = [
            repo
            for repo in repos
            if repo.get("project_name") == self.repo
            or repo.get("full_name") == self.repo
            or (
                repo.get("full_name")
                and re.search(f"(?<=/){self.repo}$", repo.get("full_name"))
            )
        ]
        user: Mapping
        matching_repos_users: List[Tuple[Mapping, Mapping]] = []
        for repo in matching_repos:
            users: Sequence[Mapping] = self.jsonrpc(
                "https://www.odoo.sh/support/json/repo_users", {"repository_id": repo["id"]}
            )
            matching_users: List[Mapping] = [
                user for user in users if user.get("username") == self.github_user
            ]
            if len(matching_users) == 1:
                [user] = matching_users
                matching_repos_users.append((repo, user))
        if len(matching_repos_users) != 1:
            msgpart: str = "Did not find matching repo-user match"
            if len(matching_repos_users) > 1:
                msgpart = "More than one repo-user match"
            raise SupportSessionError(
                f"{msgpart} to impersonate for odoo.sh access "
                f'(for repo="{self.repo}", user="{self.github_user}")'
            )
        [(repo, user)] = matching_repos_users

        # impersonate
        impersonation_data: MutableMapping[str, str] = dict(
            csrf_token=impersonation_csrf_token,
            repository_id=repo["id"],
            hosting_user_id=user["hosting_user_id"][0],
            repository_search=f'{repo["full_name"]}+({repo["project_name"]})',
        )
        resp = self.session.post(
            "https://www.odoo.sh/support/impersonate",
            data=impersonation_data,
            headers=self.headers,
        )
        if resp.status_code != 200:
            raise SupportSessionError("Failed impersonating")


    def test_session(self):
        result = self.jsonrpc("https://www.odoo.sh/project/json/user/profile")
        if result.get("errors"):
            raise SupportSessionError("Failed getting user profile while testing session")
        logger.debug("SH session okay")

    def __extract_csrf_token(response: requests.Response) -> str:
        soup: BeautifulSoup = BeautifulSoup(response.content, "html5lib")
        return soup.find("input", attrs={"name": "csrf_token"})["value"]
