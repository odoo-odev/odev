"""Set up a new submodule on odoo.sh, Github, and in a local repo"""

import os.path
from argparse import Namespace
from contextlib import contextmanager, nullcontext
from typing import (
    Any,
    ContextManager,
    Iterator,
    List,
    Mapping,
    Optional,
    Set,
    Union,
)

import giturlparse
from git import CommandError, GitError, Repo, Submodule
from github import Repository, RepositoryKey

from odev.exceptions import GitException, InvalidArgument, OdooSHException
from odev.structures import commands
from odev.utils import github, logging


_logger: logging.Logger = logging.getLogger(__name__)


class OdooSHSubmoduleCommand(commands.OdooSHDatabaseCommand, commands.GitHubCommand):
    """
    Set up a new submodule with deploy keys in an odoo.sh project, the corresponding Github repo,
    and creates the submodule in the local git clone.
    """

    name = "submodule"
    arguments = [
        {
            "name": "module_url",
            "help": "Submodule URL",
        },
        {
            "name": "module_path",
            "nargs": "?",
            "help": "Submodule path in the local repo",
        },
        {
            "name": "module_name",
            "aliases": ["--name"],
            "metavar": "MODULE_NAME",
            "dest": "module_name",
            "help": "Submodule name in the local repo",
        },
        {
            "name": "module_branch",
            "aliases": ["--branch"],
            "metavar": "MODULE_BRANCH",
            "dest": "module_branch",
            "help": "Submodule branch to checkout for the local repo",
        },
        {
            "name": "no_local",
            "aliases": ["--no-local"],
            "action": "store_true",
            "help": "Only prepare SH project for submodule, skip local git repo steps",
        },
        {
            "name": "repo_path",
            "aliases": ["--repo-path"],
            "default": ".",
            "help": "Path to the local git repo for which to prepare the submodule. Defaults to current directory",
        },
        {
            "name": "commit",
            "aliases": ["--commit"],
            "help": "Commit to the local repo after preparing the submodule with the given message",
        },
    ]

    def __init__(self, args: Namespace):
        super().__init__(args)

        self.module_url_parsed: giturlparse.GitUrlParsed = giturlparse.parse(args.module_url)
        self.module_url: str = self.module_url_parsed.format("ssh")
        self.module_path: str = args.module_path or self.module_url_parsed.repo
        self.module_name: str = args.module_name or os.path.basename(self.module_path)
        self.module_branch: Optional[str] = args.module_branch

        self.module_repo: Repository = self.github.get_repo(
            f"{self.module_url_parsed.owner}/{self.module_url_parsed.repo}"
        )

        if args.no_local and (args.repo_path or args.commit):
            raise InvalidArgument("Arguments --repo-path and --commit are incompatible with --no-local")

        self.local_repo_path: Optional[str] = None if args.no_local else args.repo_path
        if not github.is_git_repo(self.local_repo_path):
            raise GitException(f"Path '{self.local_repo_path}' is not a valid git repo")
        self.commit_msg: Optional[str] = None if args.no_local else args.commit
        self.dont_commit: bool = not self.commit_msg

    def _create_sh_submodule(self) -> Mapping[str, Any]:
        _logger.debug(f'Fetching existing submodules configured in SH for "{self.sh_repo}"')
        matching_submodules: List[Mapping[str, Any]] = [
            submodule for submodule in self.sh_connector.get_submodules() if submodule["name"] == self.module_url
        ]
        if len(matching_submodules) > 1:
            raise OdooSHException(
                f'More than one submodule in SH project "{self.sh_repo}" ' f"matches url: {self.module_url}"
            )

        sh_submodule: Optional[Mapping[str, Any]]
        if matching_submodules:
            _logger.info(f'Re-using existing submodule in SH project "{self.sh_repo}"')
            [sh_submodule] = matching_submodules
        else:
            _logger.info(f'Creating new submodule in SH project "{self.sh_repo}"')
            sh_submodule = self.sh_connector.add_submodule(self.module_url)

        assert sh_submodule is not None
        return sh_submodule

    def _create_github_deploy_key(self, deploy_key: str) -> RepositoryKey:
        _logger.debug(f"Fetching existing deploy keys from github repo: {self.module_url}")
        existing_deploy_keys: List[RepositoryKey] = [*self.module_repo.get_keys()]

        matching_deploy_keys: List[RepositoryKey] = [key for key in existing_deploy_keys if key.key == deploy_key]
        assert len(matching_deploy_keys) <= 1

        github_key: Optional[RepositoryKey]
        if matching_deploy_keys:
            [github_key] = matching_deploy_keys
            _logger.info(f'Deploy key already exists in github repo with name "{github_key.title}"')
        else:
            key_title: str = self.sh_repo
            github_key = self.module_repo.create_key(title=key_title, key=deploy_key, read_only=True)
            _logger.info(f'Created new deploy key in github repo with name "{github_key.title}"')

        assert github_key is not None
        return github_key

    def _add_local_submodule(self, repo: Repo, paths_to_commit: Set[str]) -> Submodule:
        matching_submodules: List[Submodule] = [
            submodule
            for submodule in repo.submodules
            if submodule.path == self.module_path or submodule.name == self.module_name
        ]

        git_submodule: Submodule
        if len(matching_submodules) > 1 or (matching_submodules and matching_submodules[0].url != self.module_url):
            raise GitException(
                f"Cannot add submodule to local repo '{self.local_repo_path}', because incompatible submodules"
                "with same name or path already exist:\n"
                "\n".join(repr(submodule) for submodule in matching_submodules)
            )

        elif matching_submodules:
            [git_submodule] = matching_submodules
            _logger.info(f'Re-using existing "{git_submodule.name}" submodule in local repo "{self.local_repo_path}"')

        else:
            _logger.info(f'Adding new "{self.module_name}" submodule to local repo "{self.local_repo_path}"')
            git_submodule = repo.create_submodule(
                name=self.module_name,
                path=self.module_path,
                url=self.module_url,
                branch=self.module_branch,
            )

        paths_to_commit |= {".gitmodules", git_submodule.path}

        return git_submodule

    # TODO: consider moving to utils.github ?
    @contextmanager
    def _git_commit_context(
        self, repo: Union[str, Repo], message: str, stash: bool = True, ignore_empty: bool = True
    ) -> Iterator[Set[str]]:
        if isinstance(repo, str):
            repo = Repo(self.local_repo_path)

        assert isinstance(repo, Repo)

        if stash:
            _logger.debug("Stashing non-submodule related changes")
            stash_msg: str = repo.git.stash("push")
            if "No local changes to save".lower() in stash_msg.lower():
                stash = False

        paths_to_commit: Set[str] = set()
        yield paths_to_commit

        for path in paths_to_commit:
            repo.git.add(path)
        paths_to_commit.clear()

        try:
            repo.git.commit("-m", message)
        except CommandError as exc:
            if ignore_empty and "nothing added to commit" in str(exc):
                _logger.debug("Nothing to commit for changes in local repo")
            else:
                raise

        if stash:
            _logger.debug("Un-stashing previous non-submodule related changes")
            repo.git.stash("pop")

    def _process_local_repo(self) -> None:
        assert self.local_repo_path

        repo: Repo = Repo(self.local_repo_path)

        commit_context: ContextManager[Set[str]]
        if not self.dont_commit:
            commit_context = self._git_commit_context(repo, self.commit_msg)
        else:
            commit_context = nullcontext(set())

        paths_to_commit: Set[str]
        with commit_context as paths_to_commit:
            git_submodule: Submodule = self._add_local_submodule(repo, paths_to_commit)

        if not self.dont_commit:
            _logger.info(f'Created commit for new "{git_submodule.name}" submodule: {self.commit_msg}')

    def run(self) -> int:
        sh_submodule: Mapping[str, Any] = self._create_sh_submodule()

        deploy_key: str = sh_submodule["deploy_key_public"]
        _logger.info(
            f"Using SH-generated public key to set up github deploy key for repo at: {self.module_url} "
            f"(fingerprint: {sh_submodule['deploy_key_public_fingerprint']})"
        )

        try:
            self._create_github_deploy_key(deploy_key)
        except Exception:
            _logger.warning(
                "There was an error adding the deploy key on github (access rights?), but the SH submodule "
                "was already created. It will be reused the next time you run this command, but if you need "
                f"to add the github deploy key manually, this is the SH-generated public key:\n{deploy_key}"
            )
            raise

        if self.local_repo_path:
            self._process_local_repo()

        return 0
