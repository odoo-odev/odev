import os
import re
from argparse import Namespace
from typing import (
    Any,
    Dict,
    List,
    Mapping,
    Optional,
    Sequence,
)

import Levenshtein as lev
import tldextract
from git import Repo
from giturlparse import parse

from odev.structures import commands
from odev.utils import logging
from odev.utils.github import git_clone, git_pull, is_git_repo
from odev.utils.odoo import is_saas_db
from odev.utils.shconnector import ShConnector, get_sh_connector


_logger = logging.getLogger(__name__)

MIN_LEVENSTHEIN_SCORE = 1
MAX_CHOICE_NUMBER = 3

RE_BRANCH_VERSION = re.compile(r"^([a-z~0-9]+\.[0-9]+-)")


class CloneCommand(commands.Command):
    """
    Clone a repository either with the github url or database url.
    """

    name = "clone"
    database_required = False
    arguments = [
        {
            "name": "url",
            "help": "Repo or database URL",
        },
        {
            "aliases": ["branch"],
            "help": "Branch name",
            "nargs": "?",
            "default": "",
        },
    ]

    platform = ""
    path = None

    def __init__(self, args: Namespace):
        super().__init__(args)
        no_cache_extract = tldextract.TLDExtract(cache_dir=False)
        self.url_info = no_cache_extract(self.args.url)

    def run(self):
        is_github_url = self.url_info.domain == "github"
        is_saas_url = is_github_url or is_saas_db(self.args.url)

        clone_or_find = f'{"clone" if is_github_url else "find"} the {"branch" if is_saas_url else "repository"}'

        _logger.info(f"Trying to {clone_or_find} on github for {self.args.url}")

        repo = self.select_repo("github" if is_github_url else ("saas" if is_saas_url else "sh"))
        self.clone(repo)
        return 0

    def select_repo(self, url_type: str, silent: bool = False) -> Dict[str, Any]:
        assert url_type in ["github", "saas", "sh"]
        repo_type = "repository"

        if url_type == "github":
            repo: Any = parse(self.args.url)
            repos = [{"repo": f"{repo.owner}/{repo.repo}", "organization": repo.owner, "branch": self.args.branch}]
        elif url_type == "saas":
            repo_type = "branch"
            repos = self._get_saas_repo()
        else:  # url_type == "sh"
            repos = self._get_sh_repo()

        if not repos:
            if not silent:
                _logger.warning(f"No {repo_type} found for {self.args.url}")
            return {}

        if len(repos) > 1:
            text = f"Found multiple {repo_type} for database : {self.args.url} :"
            repos = sorted(repos[0:MAX_CHOICE_NUMBER], key=lambda r: r["branch"], reverse=True)

            for index, ref in enumerate(repos):
                text += f"\n  {str(index + 1)}) {ref['branch'] or ref['db_name']} ({str(ref['repo'])})"

            _logger.info(text)
            choice = _logger.ask("Please choose the correct one ? ", "1", list(map(str, range(1, MAX_CHOICE_NUMBER))))

            repos = [repos[int(choice) - 1]]

        return repos[0]

    def _get_saas_repo(self) -> List[Dict[str, Any]]:
        # To use PyGithub we need to be inside a repository
        odev_path = self.config["odev"].get("paths", "odev")
        odev_repo = Repo(odev_path)
        saas_repo = (self.config["odev"].get("repos", "saas_repos") or "").split(",")
        repos: List[Dict[str, Any]] = []

        for ps_repo in saas_repo:
            organization = ps_repo.split("/")[0]
            branch_list = odev_repo.git.ls_remote("--heads", f"git@github.com:{ps_repo}.git")

            branches = [
                {
                    "repo": ps_repo,
                    "organization": organization,
                    "branch": b.split("/")[-1],
                    "db_name": RE_BRANCH_VERSION.sub("", b.split("/")[-1]),
                    "levenshtein": lev.distance(  # type: ignore
                        self.url_info.subdomain,
                        RE_BRANCH_VERSION.sub("", b.split("/")[-1]),
                    ),
                    "saas": True,
                }
                for b in branch_list.split("\n")
            ]

            repos = repos + self._filter(branches)

            # If we have found result on psbe-custom don't need to parse on ps-custom repo
            if repos:
                break

        return repos

    def __filter_repos_by_name(
        self, key: str, pattern: re.Pattern, repos: Optional[Sequence[Mapping[str, Any]]] = None
    ) -> List[Mapping[str, Any]]:
        repos = repos or get_sh_connector().repos
        return [repo for repo in repos if pattern.match(repo[key])]

    def _get_sh_repo(self) -> List[Dict[str, Any]]:
        sh_connector = get_sh_connector()

        if not sh_connector.repos:
            _logger.error("Can't retrieve the repositories list from Odoo SH support page")

        sh_repos = self.__filter_repos_by_name(
            "full_name",
            re.compile(rf"[a-z0-9\-]+\/(ps(ae|hk|be|us)?\-)?{self.url_info.subdomain}$", re.IGNORECASE),
            sh_connector.repos,
        ) or self.__filter_repos_by_name(
            "project_name",
            re.compile(re.escape(self.url_info.subdomain), re.IGNORECASE),
            sh_connector.repos,
        )

        repos: List[Dict[str, Any]] = [
            {
                "repo": repo["full_name"],
                "organization": repo["full_name"].split("/")[0],
                "branch": "",
                "db_name": repo["project_name"],
                "levenshtein": lev.distance(self.url_info.subdomain, repo["project_name"]),  # type: ignore
            }
            for repo in sh_repos
        ]

        return self._filter(repos) if len(repos) > 1 else repos

    def _filter(self, repos) -> List[Dict[str, Any]]:
        repos_match_lev = []
        repos = sorted(repos, key=lambda b: b["levenshtein"])

        for repo in repos[:MAX_CHOICE_NUMBER]:
            if repo["levenshtein"] == 0:
                return [repo]
            elif repo["levenshtein"] < MIN_LEVENSTHEIN_SCORE:
                repos_match_lev.append(repo)

        return repos_match_lev

    def clone(self, repo: Mapping[str, Any]):
        dir_name = ""
        devs_path = self.config["odev"].get("paths", "dev")
        parent_path = os.path.join(devs_path, repo["organization"])
        repo_path = os.path.join(devs_path, repo["repo"])

        if "saas" in repo and repo["saas"]:
            parent_path = repo_path
            repo_path = os.path.join(repo_path, repo["branch"])
            dir_name = repo["branch"]

        self.globals_context["repo_git_path"] = repo_path

        type_repo = f"branch {repo['branch']} from" if repo["branch"] else "repository"

        if is_git_repo(repo_path):
            if _logger.confirm(f"The {type_repo} {repo['repo']} already exists, do you want to pull changes now?"):
                git_pull(repo_path, repo["branch"], repo["repo"])
        else:
            _logger.info(f"The {type_repo} {repo['repo']} will be cloned to {repo_path}")
            git_clone(
                parent_path,
                repo["repo"],
                repo["branch"],
                organization=repo["organization"],
                repo_dir_name=dir_name,
            )
