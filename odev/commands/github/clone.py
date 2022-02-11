import os
import re
from argparse import Namespace

import Levenshtein as lev
import tldextract
from git import Repo
from giturlparse import parse

from odev.structures import commands
from odev.utils import logging
from odev.utils.github import git_clone, git_pull
from odev.utils.odoo import is_saas_db
from odev.utils.shconnector import ShConnector, get_sh_connector

_logger = logging.getLogger(__name__)

MIN_LEVENSTHEIN_SCORE = 3
MAX_CHOICE_NUMBER = 3

RE_BRANCH_VERSION = re.compile(r"^([a-z~0-9]+\.[0-9]+-)")

class CloneCommand(commands.Command):
    """
    Clone a repository either with the github url or database url.
    """

    name = "clone"
    database_required = False
    arguments = [
        dict(
            name="url",
            help="Repo or database URL",
        ),
        dict(
            aliases=["branch"],
            help="Branch name",
            nargs="?",
            default="",
        ),
    ]

    platform = ""
    path = None

    def __init__(self, args: Namespace):
        super().__init__(args)
        no_cache_extract = tldextract.TLDExtract(cache_dir=False)
        self.url_info = no_cache_extract(self.args.url)

    def run(self):
        repos = []

        is_github_url = self.url_info.domain == "github"
        is_saas_url = is_github_url or is_saas_db(self.args.url)

        clone_or_find = f'{"clone" if is_github_url else "find"} the {"branch" if is_saas_url else "repository"}'

        _logger.info(f"Trying to {clone_or_find} on github for {self.args.url} .")

        if is_github_url:
            repo = parse(self.args.url)
            repos = [{"repo": f"{repo.owner}/{repo.repo}", "organization": repo.owner, "branch": self.args.branch}]

        elif is_saas_url:
            repos = self._get_saas_repo()
        else:
            repos = self._get_sh_repo()

        if len(repos) > 1:
            text = f'Found multiple {"branch" if is_saas_url else "repository"} for database : {self.args.url} :'
            repos = sorted(repos[0:MAX_CHOICE_NUMBER], key=lambda r: r["branch"], reverse=True)

            for index, ref in enumerate(repos):
                text = text + f"\n  {str(index + 1)}) {ref['branch'] or ref['db_name']} ({str(ref['repo'])})"

            _logger.info(text)
            choice = _logger.ask("Please choose the correct one ? ", "1", list(map(str, range(1, MAX_CHOICE_NUMBER))))

            repos = [repos[int(choice) - 1]]

        if not repos:
            _logger.warning(f'No {"branch" if is_saas_url else "repository"} found for database : {self.args.url}')
            return 1

        self.clone(repos[0])

        return 0

    def _get_saas_repo(self):
        # To use PyGithub we need to be inside a repository
        odev_path = self.config['odev'].get("paths", "odev")
        odev_repo = Repo(odev_path)
        saas_repo = (self.config["odev"].get("repos", "saas_repos") or "").split(",")
        repos = []

        for ps_repo in saas_repo:
            # TODO: Use giturlparse ?
            organization = ps_repo.split("/")[0]
            branch_list = odev_repo.git.ls_remote("--heads", f"git@github.com:{ps_repo}.git")

            branches = [
                {
                    "repo": ps_repo,
                    "organization": organization,
                    "branch": b.split("/")[-1],
                    "db_name": RE_BRANCH_VERSION.sub("", b.split("/")[-1]),
                    "levenshtein": lev.distance(
                        self.url_info.subdomain, RE_BRANCH_VERSION.sub("", b.split("/")[-1])
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

    def _get_sh_repo(self):
        sh_connector: ShConnector = get_sh_connector()

        if not sh_connector.repos:
            _logger.error("Can't retreive the repo list from odoo.sh support page")

        repos = [
            {
                "repo": f"{x['full_name']}",
                "organization": x["full_name"].split("/")[0],
                "branch": "",
                "db_name": x["project_name"],
                "levenshtein": lev.distance(self.url_info.subdomain, x["project_name"]),
            }
            for x in sh_connector.repos
        ]

        return self._filter(repos)

    def _filter(self, repos):
        repos_match_lev = []
        repos = sorted(repos, key=lambda b: b["levenshtein"])

        for repo in repos[:MAX_CHOICE_NUMBER]:
            if repo["levenshtein"] == 0:
                return [repo]
            elif repo["levenshtein"] < MIN_LEVENSTHEIN_SCORE:
                repos_match_lev.append(repo)

        return repos_match_lev

    def clone(self, repo: str):
        dir_name = ""
        devs_path = self.config["odev"].get("paths", "dev")
        parent_path = os.path.join(devs_path, repo["organization"])
        repo_path = os.path.join(devs_path, repo["repo"])

        if "saas" in repo and repo["saas"]:
            parent_path = repo_path
            repo_path = os.path.join(repo_path, repo["branch"])
            dir_name = repo["branch"]

        type_repo = f"branch {repo['branch']} from" if repo["branch"] else "repo"

        if os.path.exists(repo_path):
            if _logger.confirm(f"The {type_repo} {repo['repo']} already exist, do you to pull ?"):
                git_pull(repo_path, repo["branch"])
        else:

            _logger.info(f"The {type_repo} {repo['repo']} will lbe cloned into {devs_path}")
            git_clone(
                parent_path, repo["repo"], repo["branch"], organization=repo["organization"], repo_dir_name=dir_name
            )

        self.globals_context['repo_git_path'] = repo_path
