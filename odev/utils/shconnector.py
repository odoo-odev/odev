import logging
import shlex
import subprocess
import sys

import requests
from bs4 import BeautifulSoup


__all__ = ["ShConnector"]


logger = logging.getLogger(__name__)


class ShConnector(object):
    def __init__(self, login, password):
        self.session = self.create_session(login, password)

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

    def post(self, model, method, args, kwargs={}, retry=True):
        url = "https://www.odoo.sh/web/dataset/call_kw/%s/%s" % (model, method)
        data = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "model": model,
                "method": method,
                "args": args,
                "kwargs": kwargs,
            },
        }
        resp = False
        try:
            resp = self.session.post(url=url, json=data)
            return resp.json()["result"]
        except Exception:
            # probably too hardcore
            if retry:
                self.post(model, method, args, kwargs={}, retry=False)
            logger.error(data)
            if resp:
                logger.error(resp.text)

    def _get_branch_id(self, repo, branch):
        branch_id = self.post(
            "paas.branch",
            "search",
            [[["name", "=", "%s" % branch], ["repository_id.name", "=", "%s" % repo]]],
        )
        if not branch_id:
            raise ValueError("Branch %s not found on repo %s" % (branch, repo))
        return branch_id

    def change_branch_state(self, repo, branch, state):
        """
        Switch a branch from staging to dev or the other way around
        """
        if state not in ("dev", "staging"):
            raise ValueError("You must choose dev or staging")

        branch_id = self._get_branch_id(repo, branch)
        self.post("paas.branch", "write", [branch_id, {"stage": state}])
        logger.info("%s: %s -> %s" % (repo, branch, state))

    def build_status(self, repo, branch, commit=False):
        """
        Returns status, hash and creation date of last build on given branch
        (but you can force status search of a specific commit if you need to time travel)
        """
        branch_id = self._get_branch_id(repo, branch)
        domain = [["branch_id", "=", branch_id]]
        if commit:
            domain += [["head_commit_id.identifier", "=", "%s" % commit]]
        res = self.post(
            "paas.build",
            "search_read",
            [domain, ["result", "status", "head_commit_id", "create_date"]],
            {"limit": 1},
        )
        return res and res[0]

    def get_stagings(self, repo):
        """
        Returns staging branches name
        """
        return self.post(
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
        return self.post(
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

    def get_last_build_ssh(self, repo, branch):
        """
        Returns ssh
        """
        branch_id = self._get_branch_id(repo, branch)
        vals = self.post(
            "paas.branch", "search_read", [[("id", "=", branch_id)], ["last_build_id"]]
        )
        if vals:
            vals = vals[0]["last_build_id"]
            return "%s@%s.dev.odoo.com" % (vals[0], vals[1])

    @staticmethod
    def ssh_command(
        ssh_url,
        command=None,
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
        if script:
            command = script_shell
            stdin_data = script
        else:
            stdin_data = None
        if isinstance(command, (list, tuple)):
            command = shlex.join(command)
        kwargs.setdefault("stdout", logfile)
        kwargs.setdefault("stderr", logfile)
        if stdin_data is None:
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
