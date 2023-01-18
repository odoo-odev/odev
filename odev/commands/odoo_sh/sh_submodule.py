"""Set up a new submodule on odoo.sh, Github, and in a local repo"""

import os.path
import re
from argparse import Namespace
from contextlib import nullcontext
from typing import (
    Any,
    ClassVar,
    ContextManager,
    List,
    Mapping,
    Optional,
    Tuple,
)

import giturlparse
from git import Repo, Submodule
from github import Repository, RepositoryKey

from odev.exceptions import GitException, InvalidArgument, OdooSHException
from odev.structures import commands
from odev.utils import github, logging
from odev.utils.github import GitCommitContext


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
            "nargs": "?",
            "default": None,  # no arg passed
            "const": True,  # no value passed
            "help": "Commit to the local repo after preparing the submodule with the given message",
        },
        {
            "name": "update",
            "aliases": ["--update"],
            "nargs": "?",
            "default": None,  # no arg passed
            "const": True,  # no value passed
            "help": "If the submodule exists locally, update it from remote with the given commit message",
        },
    ]

    default_commit_msg: ClassVar[Optional[str]] = "[ADD] add `{module_name}` submodule"
    default_update_msg: ClassVar[Optional[str]] = "[IMP] update `{module_name}` submodule to {module_commit}"

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

        self.to_commit: bool = bool(args.commit)
        if args.commit in (True, None):
            args.commit = self.default_commit_msg
        self.commit_msg: Optional[str] = args.commit

        self.to_update: bool = bool(args.update)
        if args.update in (True, None):
            args.update = self.default_update_msg
        self.update_msg: Optional[str] = args.update

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

    def _add_local_submodule(self, repo: Repo, commit_context: Optional[GitCommitContext]) -> Tuple[Submodule, bool]:
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

        git_submodule.update(init=True)

        just_added: bool = not matching_submodules

        if just_added and commit_context is not None:
            commit_context.add(".gitmodules", git_submodule.path)

        return git_submodule, just_added

    def _update_local_submodule(self, git_submodule: Submodule, commit_context: Optional[GitCommitContext]) -> bool:
        if not self.to_update:
            if _logger.confirm(
                "The submodule already exists in the local repo. Do you want to update it to the latest version?"
            ):
                self.to_update = True
                if commit_context is not None:
                    if not self.update_msg and self.default_update_msg:
                        self.update_msg = self.default_update_msg
                    if not self.update_msg:
                        self.update_msg = _logger.ask("Specify a commit message for the submodule update:")
                        if not self.update_msg:
                            raise InvalidArgument("Cannot commit without a message")

        if not self.to_update:
            return False

        submodule_repo: Repo = git_submodule.module()
        if submodule_repo.head.is_detached:
            # find main branch on remote and switch to it
            remote_details: str = submodule_repo.git.remote("show", submodule_repo.remotes[0].name)
            match: Optional[re.Match] = re.search(r"^\s*HEAD branch:\s*([^\s]+)", remote_details, flags=re.M)
            if not match:
                _logger.error("Couldn't determine main remote branch for submodule repo")
                return False
            main_branch: str = match.group(1)
            submodule_repo.git.switch(main_branch)

        sha_before: str = git_submodule.hexsha
        git_submodule.update(to_latest_revision=True)
        sha_after: str = submodule_repo.head.commit.hexsha

        updated: bool = sha_after != sha_before

        if updated:
            if commit_context is not None:
                commit_context.add(git_submodule.path)
            _logger.info(f'Updated "{self.module_name}" submodule to commit {sha_after[:7]}')
        else:
            _logger.info("Submodule already up to date, nothing to do")

        return updated

    def _conditional_commit_context(self, *args, **kwargs) -> ContextManager[Optional[GitCommitContext]]:
        return GitCommitContext(*args, **kwargs) if self.to_commit else nullcontext()

    def _format_commit_msg(self, msg_template: Optional[str], **values) -> str:
        if not msg_template:
            return ""
        return msg_template.format(
            module_url=self.module_url,
            module_path=self.module_path,
            module_name=self.module_name,
            module_branch=self.module_branch,
            module_url_domain=self.module_url_parsed.domain,
            module_url_repo=self.module_url_parsed.repo,
            module_url_owner=self.module_url_parsed.owner,
            module_url_platform=self.module_url_parsed.platform,
            module_url_protocol=self.module_url_parsed.protocol,
            **values,
        )

    def _process_local_repo(self) -> None:
        assert self.local_repo_path

        repo: Repo = Repo(self.local_repo_path)

        commit_context: Optional[GitCommitContext]
        git_submodule: Submodule
        just_added: bool
        updated: bool = False
        log_msg_type: Optional[str] = None
        with self._conditional_commit_context(repo) as commit_context:
            git_submodule, just_added = self._add_local_submodule(repo, commit_context)

            if not just_added:
                updated = self._update_local_submodule(git_submodule, commit_context)

            if commit_context is not None:
                commit_msg_template: Optional[str] = None
                extra_values: Mapping[str, Any]
                if just_added:
                    commit_msg_template = self.commit_msg
                    extra_values = {"module_commit": git_submodule.hexsha}
                    log_msg_type = "added"
                elif updated:
                    commit_msg_template = self.update_msg
                    extra_values = {
                        "module_commit": git_submodule.module().head.commit.hexsha[:7],
                        "module_commit_before": git_submodule.hexsha,
                    }
                    log_msg_type = "updated"
                if commit_msg_template:
                    commit_msg = self._format_commit_msg(commit_msg_template, **extra_values)
                    commit_context.message = commit_msg

        if log_msg_type:
            _logger.info(f'Created commit for {log_msg_type} "{git_submodule.name}" submodule: {commit_msg}')

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
