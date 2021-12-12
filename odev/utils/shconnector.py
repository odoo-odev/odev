import re
import shlex
import subprocess
import sys
from typing import Optional, List, MutableMapping, Any, Tuple, Mapping, Sequence

import requests
from bs4 import BeautifulSoup

from odev.utils import logging
from odev.utils.credentials import CredentialsHelper


__all__ = ["ShConnector", "get_sh_connector"]


logger = logging.getLogger(__name__)


class ShError(Exception):
    """Base class for SH errors"""


class ShSessionError(ShError):
    """Session-related SH errors (es. expired cookie)"""


class ShConnector(object):
    def __init__(self, login: str, passwd: str, repo_name: str, github_user: str):
        self.login: str = login
        self.repo: str = repo_name
        self.github_user: str = github_user
        self.session: Optional[requests.Session] = None

        self.login_impersonate(passwd)

        self.test_session()

    def login_impersonate(self, passwd: str) -> None:
        headers: MutableMapping[str, str] = {
            "user-agent": "odev (https://github.com/odoo-ps/psbe-ps-tech-tools/tree/odev)"
        }

        impersonate_page_url = "/_odoo/support"

        self.session = requests.Session()
        resp: requests.Response

        def extract_csrf_token(response: requests.Response) -> str:
            soup: BeautifulSoup = BeautifulSoup(response.content, "html5lib")
            return soup.find("input", attrs={"name": "csrf_token"})["value"]

        # do login
        login_data: MutableMapping[str, str] = {
            "redirect": impersonate_page_url,
            "login": self.login,
            "password": passwd,
        }
        resp = self.session.get(
            f"https://www.odoo.sh/web/login?debug=1&redirect={impersonate_page_url}",
            headers=headers,
        )
        login_data["csrf_token"] = extract_csrf_token(resp)

        resp = self.session.post(
            "https://www.odoo.sh/web/login", data=login_data, headers=headers
        )
        if resp.status_code != 200:
            raise ShSessionError("Failed logging in to odoo.sh")

        if impersonate_page_url not in resp.url:
            raise ShSessionError(
                f"Unexpected redirect for impersonation page, got: {resp.url}"
            )
        impersonation_csrf_token: str = extract_csrf_token(resp)

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
            raise ShSessionError(
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
            headers=headers,
        )
        if resp.status_code != 200:
            raise ShSessionError("Failed impersonating")

    @property
    def session_id(self):
        return self.session.cookies.get("session_id", domain="www.odoo.sh")

    def jsonrpc(
        self, url, params=None, method="call", version="2.0", allow_empty=True, retry=False
    ):
        if params is None:
            params = {}
        data = {
            "jsonrpc": version,
            "method": method,
            "params": params,
        }
        resp = None
        try:
            resp = self.session.post(url=url, json=data)
            resp_data = resp.json()
        except Exception:  # FIXME: too broad?
            # probably too hardcore
            if retry:
                return self.jsonrpc(url, params, method=method, version=version, retry=retry)
            else:
                logger.exception(data)
                if resp:
                    logger.error(resp.text)
                raise

        if not ("result" in resp_data if allow_empty else resp_data.get("result")):
            error = resp_data.get("error")
            if error:
                error_message = error.get("message")
                if "Session Expired" in error_message:
                    raise ShSessionError("Odoo.sh Session Expired")
                raise ShError(error_message)
            raise ShError(f"Bad response from SH: {resp_data}")

        return resp_data["result"]

    def call_kw(self, model, method, args, kwargs=None, retry=False):
        if kwargs is None:
            kwargs = {}
        url = "https://www.odoo.sh/web/dataset/call_kw/%s/%s" % (model, method)
        params = {
            "model": model,
            "method": method,
            "args": args,
            "kwargs": kwargs,
        }
        return self.jsonrpc(url, params=params, retry=retry)

    def test_session(self):
        result = self.jsonrpc("https://www.odoo.sh/project/json/user/profile")
        if result.get("errors"):
            raise ShSessionError("Failed getting user profile while testing session")
        logger.debug("SH session okay")

    def _get_branch_id(self, branch):
        branch_id = self.call_kw(
            "paas.branch",
            "search",
            [[["name", "=", "%s" % branch], ["repository_id.name", "=", self.repo]]],
        )
        if not branch_id:
            raise ValueError("Branch %s not found on repo %s" % (branch, self.repo))
        return branch_id

    def _get_last_build_id_name(self, branch):
        branch_id = self._get_branch_id(branch)
        vals = self.call_kw(
            "paas.branch", "search_read", [[("id", "=", branch_id)], ["last_build_id"]]
        )
        if vals:
            last_build_id = vals[0].get("last_build_id")
            if last_build_id:
                build_id, build_name = vals[0]["last_build_id"]
                return build_id, build_name
        return None

    def project_info(self) -> Optional[MutableMapping[str, Any]]:
        """
        Return information about an odoo.sh project (repository), or None.
        """
        results: List[MutableMapping[str, Any]] = self.call_kw(
            "paas.repository",
            "search_read",
            [
                [["name", "=", self.repo]],
                [],
            ],
        )
        if not results:
            return None
        if len(results) > 1:
            raise ValueError(f'Got more than 1 result for repo "{self.repo}":\n{results}')
        return results[0]

    def branch_info(self, branch: str) -> Optional[MutableMapping[str, Any]]:
        """
        Return information about an odoo.sh branch, or None.
        """
        results: List[MutableMapping[str, Any]] = self.call_kw(
            "paas.branch",
            "search_read",
            [
                [["repository_id.name", "=", self.repo], ["name", "=", branch]],
                [],
            ],
        )
        if not results:
            return None
        if len(results) > 1:
            raise ValueError(f'Got more than 1 result for branch "{branch}":\n{results}')
        return results[0]

    def branch_history(self, branch: str, custom_domain: Optional[List] = None) -> Optional[List[MutableMapping[str, Any]]]:
        """
        Return history tracking info of an odoo.sh branch, or None.
        """
        domain = [["repository_id.name", "=", self.repo], ["branch_id.name", "=", branch]]
        domain += custom_domain or []
        results: List[MutableMapping[str, Any]] = self.call_kw(
            "paas.tracking",
            "search_read",
            [
                domain,
                [],
            ],
            # dict(order="start_datetime desc"),  # TODO: Check default order is okay
        )
        return results or None

    def change_branch_state(self, branch, state):
        """
        Switch a branch from staging to dev or the other way around
        """
        if state not in ("dev", "staging"):
            raise ValueError("You must choose dev or staging")

        branch_id = self._get_branch_id(branch)
        self.call_kw("paas.branch", "write", [branch_id, {"stage": state}])
        logger.info("%s: %s -> %s" % (self.repo, branch, state))

    def branch_rebuild(self, branch):
        """
        Rebuild a branch.
        """
        project_info = self.project_info()
        project_url: str = project_info["project_url"]
        return self.jsonrpc(f"{project_url}/branch/rebuild", params={"branch": branch})

    def build_info(self, branch, build_id=None, commit=None, custom_domain=None):
        """
        Returns status, hash and creation date of last build on given branch
        (but you can force status search of a specific commit if you need to time travel)
        """
        if build_id and commit:
            raise AttributeError('Only one of "build_id" or "commit" can be specified')
        domain = []
        if build_id or commit:
            branch_id = self._get_branch_id(branch)
            domain += [["branch_id", "=", branch_id]]
            if commit:
                domain += [["head_commit_id.identifier", "=", str(commit)]]
            else:
                domain += [["id", "=", int(build_id)]]
        elif not custom_domain:
            result = self._get_last_build_id_name(branch)
            if not result:
                return None
            last_build_id, _ = result
            domain += [["id", "=", last_build_id]]
        if custom_domain:
            domain += custom_domain
        res = self.call_kw(
            "paas.build",
            "search_read",
            [
                domain,
                [],
            ],
            dict(limit=1, order="start_datetime desc"),
        )
        return res and res[0]

    build_status = build_info

    def get_stagings(self):
        """
        Returns staging branches name
        """
        return self.call_kw(
            "paas.branch",
            "search_read",
            [
                [["stage", "=", "staging"], ["repository_id.name", "=", self.repo]],
                ["name"],
            ],
        )

    def get_prod(self):
        """
        Returns prod branch
        """
        return self.call_kw(
            "paas.branch",
            "search_read",
            [
                [
                    ["stage", "=", "production"],
                    ["repository_id.name", "=", self.repo],
                ],
                ["name"],
            ],
        )

    def get_project_info(self):
        return self.call_kw(
            "paas.repository",
            "search_read",
            [
                [["name", "=", self.repo]],
                [],
            ],
        )

    def get_build_ssh(self, branch, build_id=None, commit=None):
        """
        Returns ssh
        """
        if build_id or commit:
            build_info = self.build_info(branch, build_id=build_id, commit=commit)
            if not build_info:
                if build_id:
                    msgpart = build_id
                else:
                    msgpart = f"on commit {commit}"
                raise ValueError(f"Couldn't get info for build {msgpart} on {branch}")
            build_id, build_name = build_info["id"], build_info["name"]
        else:
            result = self._get_last_build_id_name(branch)
            if not result:
                return None
            build_id, build_name = result
        return f"{build_id}@{build_name}.dev.odoo.com"

    def get_last_build_ssh(self, branch):
        """
        Returns ssh
        """
        return self.get_build_ssh(branch)

    @staticmethod
    def ssh_command(
        ssh_url,
        command=None,
        stdin_data=None,
        script=None,
        script_shell="bash -s",
        check=True,
        logfile=sys.stdout,
        **kwargs,
    ):
        """
        Runs an command or script through SSH in the specified SH branch.

        :param ssh_url: the ssh url of the odoo.sh branch.
            Must be omitted if ``repo`` and ``branch`` are provided.
        :param command: the command to run through SSH. Can be a string or a
            list of strings that will be assembled in a single command line.
            Must be omitted if using ``script`` instead.
        :param stdin_data: data to pass as stdin to the command over ssh.
        :param script: a script to run through SSH.
            Must be omitted if using ``command`` instead.
        :param script_shell: the shell command to use to pass the ``script`` to.
            Defaults to `bash -s`.
        :param check: check the returncode of the SSH subprocess. Defaults to `True`.
        :param logfile: a buffer to use for the SSH subprocess stderr/stdout.
            Defaults to `sys.stdout`.
        :param kwargs: additional keyword arguments for :func:`subprocess.run()`
        :return: a :class:`subprocess.CompletedProcess` object.
        """
        if not command and not script:
            raise AttributeError('Must provide at least one of "command" or "script"')
        elif command and script:
            raise AttributeError('Must provide only one of "command" or "script"')
        if script and stdin_data:
            raise AttributeError('Cannot use both "script" and "stdin_data"')
        if script:
            command = script_shell
            stdin_data = script
        if isinstance(command, (list, tuple)):
            command = shlex.join(command)
        kwargs.setdefault("stdout", logfile)
        kwargs.setdefault("stderr", logfile)
        if script is None:
            logger.debug(f"Running ssh command on SH build {ssh_url}: {command}")
        else:
            logger.debug(
                f"Running {command.split(' ')[0]} script through ssh on SH build {ssh_url}"
            )
        return subprocess.run(
            ["ssh", ssh_url, "-o", "StrictHostKeyChecking=no", command],
            input=stdin_data,
            check=check,
            **kwargs,
        )

    def ssh_command_last_build(self, branch, *args, **kwargs):
        """
        Runs an command or script through SSH in the latest build of a SH branch.

        :param repo: the name of the repo / odoo.sh project.
            Include with ``branch`` if not passing a ``ssh_url``.
        :param branch: the name of the branch in the odoo.sh project.
            Include with ``repo`` if not passing a ``ssh_url``.
        :param args: additional positional arguments for :func:`ssh_command`
        :param kwargs: additional keyword arguments for :func:`ssh_command`
        :return: whatever the :func:`ssh_command` call returns
        """
        ssh_url = self.get_last_build_ssh(branch)
        return self.ssh_command(ssh_url, *args, **kwargs)


# TODO: Maybe move this fn that's more related to secrets storage outside this module
def get_sh_connector(
    login: Optional[str] = None,
    passwd: Optional[str] = None,
    repo_name: Optional[str] = None,
    github_user: Optional[str] = None,
) -> ShConnector:
    with CredentialsHelper() as creds:
        login = creds.get("odoo.login", "Odoo login:", login)
        passwd = creds.secret("odoo.passwd", f"Odoo password for {login}:", passwd)
        github_user = creds.get("github.user", "GitHub username:", github_user)
        return ShConnector(login, passwd, repo_name, github_user)
