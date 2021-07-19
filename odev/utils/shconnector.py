import logging
import shlex
import subprocess
import sys
from contextlib import nullcontext
from typing import Optional, ContextManager, List, MutableMapping, Any

import requests
from bs4 import BeautifulSoup

from .secrets import secret_storage, StoreSecret
from .utils import ask, password


__all__ = ["ShConnector", "get_sh_connector"]


logger = logging.getLogger(__name__)


class ShConnector(object):
    def __init__(self, login, password, session_id=None):
        got_login = bool(login and password)
        login_valid = bool(login) and bool(password)
        if got_login == bool(session_id) or (got_login and not login_valid):
            raise AttributeError('Must provide either "login" and "password" or a "session_id"')
        if got_login:
            self.session = self.create_session(login, password)
            if not self.session_id:
                raise ValueError("Failed authentication to odoo.sh")
        else:
            self.session = requests.Session()
            self.session.cookies.set("session_id", session_id, domain="www.odoo.sh")

    def create_session(self, login, password):
        headers = {
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/73.0.3683.86 Safari/537.36"
        }

        login_data = {
            "commit": "Sign in",
            "utf8": "%E2%9C%93",
            "login": login,
            "password": password,
        }

        session = requests.Session()
        url = "https://github.com/session"
        resp = session.get(url, headers=headers)
        soup = BeautifulSoup(resp.content, "html5lib")
        login_data["authenticity_token"] = soup.find(
            "input", attrs={"name": "authenticity_token"}
        )["value"]

        resp = session.post(url, data=login_data, headers=headers)

        # TODO : do something smarter
        if "Incorrect username or password" in resp.text:
            raise ValueError("Can't connect on Github")
        session.get("https://www.odoo.sh/project")  # get session_id cookie

        return session

    @property
    def session_id(self):
        return self.session.cookies.get("session_id", domain="www.odoo.sh")

    def jsonrpc(self, url, params=None, method="call", version="2.0", retry=False):
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
            return resp.json()["result"]
        except Exception:  # FIXME: too broad?
            # probably too hardcore
            if retry:
                self.jsonrpc(url, params, method=method, version=version, retry=retry)
            logger.error(data)
            if resp:
                logger.error(resp.text)

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

    def _get_branch_id(self, repo, branch):
        branch_id = self.call_kw(
            "paas.branch",
            "search",
            [[["name", "=", "%s" % branch], ["repository_id.name", "=", "%s" % repo]]],
        )
        if not branch_id:
            raise ValueError("Branch %s not found on repo %s" % (branch, repo))
        return branch_id

    def _get_last_build_id_name(self, repo, branch):
        branch_id = self._get_branch_id(repo, branch)
        vals = self.call_kw(
            "paas.branch", "search_read", [[("id", "=", branch_id)], ["last_build_id"]]
        )
        if vals:
            build_id, build_name = vals[0]["last_build_id"]
            return build_id, build_name
        return None

    def project_info(self, repo: str) -> Optional[MutableMapping[str, Any]]:
        """
        Return information about an odoo.sh project (repository), or None.
        """
        results: List[MutableMapping[str, Any]] = self.call_kw(
            "paas.repository",
            "search_read",
            [
                [["name", "=", repo]],
                [],
            ],
        )
        if not results:
            return None
        if len(results) > 1:
            raise ValueError(f'Got more than 1 result for repo "{repo}":\n{results}')
        return results[0]

    def branch_info(self, repo: str, branch: str) -> Optional[MutableMapping[str, Any]]:
        """
        Return information about an odoo.sh branch, or None.
        """
        results: List[MutableMapping[str, Any]] = self.call_kw(
            "paas.branch",
            "search_read",
            [
                [["repository_id.name", "=", repo], ["name", "=", branch]],
                [],
            ],
        )
        if not results:
            return None
        if len(results) > 1:
            raise ValueError(f'Got more than 1 result for branch "{branch}":\n{results}')
        return results[0]

    def change_branch_state(self, repo, branch, state):
        """
        Switch a branch from staging to dev or the other way around
        """
        if state not in ("dev", "staging"):
            raise ValueError("You must choose dev or staging")

        branch_id = self._get_branch_id(repo, branch)
        self.call_kw("paas.branch", "write", [branch_id, {"stage": state}])
        logger.info("%s: %s -> %s" % (repo, branch, state))

    def branch_rebuild(self, repo, branch):
        """
        Rebuild a branch.
        """
        project_info = self.project_info(repo)
        project_url: str = project_info["project_url"]
        return self.jsonrpc(f"{project_url}/branch/rebuild", params={"branch": branch})

    def build_info(self, repo, branch, build_id=None, commit=None):
        """
        Returns status, hash and creation date of last build on given branch
        (but you can force status search of a specific commit if you need to time travel)
        """
        if build_id and commit:
            raise AttributeError('Only one of "build_id" or "commit" can be specified')
        domain = []
        if build_id or commit:
            branch_id = self._get_branch_id(repo, branch)
            domain += [["branch_id", "=", branch_id]]
            if commit:
                domain += [["head_commit_id.identifier", "=", str(commit)]]
            else:
                domain += [["id", "=", int(build_id)]]
        else:
            result = self._get_last_build_id_name(repo, branch)
            if not result:
                return None
            last_build_id, _ = result
            domain += [["id", "=", last_build_id]]
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

    def get_stagings(self, repo):
        """
        Returns staging branches name
        """
        return self.call_kw(
            "paas.branch",
            "search_read",
            [
                [["stage", "=", "staging"], ["repository_id.name", "=", "%s" % repo]],
                ["name"],
            ],
        )

    def get_prod(self, repo):
        """
        Returns prod branch
        """
        return self.call_kw(
            "paas.branch",
            "search_read",
            [
                [
                    ["stage", "=", "production"],
                    ["repository_id.name", "=", "%s" % repo],
                ],
                ["name"],
            ],
        )

    def get_project_info(self, repo):
        return self.call_kw(
            "paas.repository",
            "search_read",
            [
                [["name", "=", repo]],
                [],
            ],
        )

    def get_build_ssh(self, repo, branch, build_id=None, commit=None):
        """
        Returns ssh
        """
        if build_id or commit:
            build_info = self.build_info(repo, branch, build_id=build_id, commit=commit)
            if not build_info:
                if build_id:
                    msgpart = build_id
                else:
                    msgpart = f"on commit {commit}"
                raise ValueError(f"Couldn't get info for build {msgpart} on {branch}")
            build_id, build_name = build_info["id"], build_info["name"]
        else:
            result = self._get_last_build_id_name(repo, branch)
            if not result:
                return None
            build_id, build_name = result
        return f"{build_id}@{build_name}.dev.odoo.com"

    def get_last_build_ssh(self, repo, branch):
        """
        Returns ssh
        """
        return self.get_build_ssh(repo, branch)

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

    def ssh_command_last_build(self, repo, branch, *args, **kwargs):
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
        ssh_url = self.get_last_build_ssh(repo, branch)
        return self.ssh_command(ssh_url, *args, **kwargs)


def get_sh_connector(
    login: Optional[str] = None,
    passwd: Optional[str] = None,
    session_id: Optional[str] = None,
) -> ShConnector:
    save: bool = False
    storage_context: ContextManager[Optional[str]] = nullcontext(session_id)
    if session_id is None:
        storage_context = secret_storage("odoosh_session_id")
    try:
        with storage_context as session_id:
            if session_id is None:
                login = ask("Github / odoo.sh login:")
                passwd = password("Github / odoo.sh password:")
                save = True
            sh_connector: ShConnector = ShConnector(login, passwd, session_id)
            session_id = sh_connector.session_id
            if save:
                raise StoreSecret(session_id)
    finally:
        pass
    return sh_connector
