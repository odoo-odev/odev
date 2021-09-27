'''Runs modules upgrades on a odoo.sh branch with `util` support.'''

import configparser
from odev.exceptions.commands import CommandAborted
import os
import subprocess
from decorator import contextmanager
from abc import ABC, abstractmethod
from argparse import Namespace
from dataclasses import dataclass
from io import StringIO
from github import Repository, PullRequest, PullRequestMergeStatus
from typing import (
    Sequence,
    List,
    Optional,
    Mapping,
    Tuple,
    Any,
    Set,
    MutableMapping,
    Iterator,
)

from odev.structures import commands
from odev.structures.actions import CommaSplitAction
from odev.utils import logging
from odev.exceptions import BuildCompleteException, BuildWarning


logger = logging.getLogger(__name__)


# TODO: do proper config
REMOTE_ODOO_HOME: str = '/home/odoo'
REMOTE_ODOO_CONFIG: str = os.path.join(REMOTE_ODOO_HOME, '.config/odoo/odoo.conf')
REMOTE_UPGRADE_DIR: str = os.path.join(REMOTE_ODOO_HOME, 'odev_upgrade_temp')

UPGRADE_UTIL_RELPATH: str = 'migrations/util'
PSBE_MIGRATIONS_RELPATH: str = 'migrations'
PSBE_UPGRADE_BASE_RELPATH: str = os.path.join(PSBE_MIGRATIONS_RELPATH, 'base')
REMOTE_UTIL_RELPATH: str = 'upgrade-util'


def edit_odoo_config_data(config_data: str, edit_data: Mapping[Tuple[Optional[str], str], Optional[str]]) -> str:
    # preserve comments (although w/out empty lines)
    parser: configparser.RawConfigParser = configparser.RawConfigParser(
        comment_prefixes=[], allow_no_value=True
    )
    parser.read_string(config_data)
    section_name: Optional[str]
    option_name: str
    option_value: Optional[str]

    for (section_name, option_name), option_value in edit_data.items():
        if section_name is None:
            section_name = parser.default_section
        if section_name not in parser:
            if option_value is None:
                continue  # we don't have section, so no option to remove too
            parser.add_section(section_name)
        if option_value is not None:
            parser.set(section_name, option_name, option_value)
        else:
            parser.remove_option(section_name, option_name)
    with StringIO() as fp:
        parser.write(fp)
        return fp.getvalue()


class OdooSHUpgradeBaseCommand(commands.OdooSHBranchCommand):
    '''
    Command class for running modules upgrades on a odoo.sh branch with `util` support.
    '''

    arguments = [
        dict(
            aliases=['--upgrade-repo-path'],
            help='Local path of the `upgrade` repository clone from which to copy `util`',
        ),
        dict(
            aliases=['--psbe-upgrade-repo-path'],
            help='Local path of the `psbe-custom-upgrade` repository clone '
            'from which `base` and `custom_utils` are copied',
        ),
        dict(
            aliases=['-r', '--remote-dir'],
            default=REMOTE_UPGRADE_DIR,
            help='Remote working directory where files are copied. Defaults to `~/tmp`',
        ),
    ]

    def __init__(self, args: Namespace):
        if args.upgrade_repo_path is None:
            raise ValueError('No `upgrade-repo-path` specified')

        self.upgrade_repo_path: str = os.path.normpath(args.upgrade_repo_path)
        self.psbe_upgrade_repo_path: str = os.path.normpath(args.psbe_upgrade_repo_path)
        self.remote_upgrade_dir: str = args.remote_dir or REMOTE_UPGRADE_DIR

        self.remote_util_path: str = os.path.join(
            self.remote_upgrade_dir, REMOTE_UTIL_RELPATH
        )
        self.remote_psbe_upgrade_path: str = os.path.join(
            self.remote_upgrade_dir, os.path.basename(self.psbe_upgrade_repo_path)
        )
        self.remote_psbe_migrations_path: str = os.path.join(
            self.remote_psbe_upgrade_path, PSBE_MIGRATIONS_RELPATH
        )
        self._prepared_upgrade_paths: Set[str] = set()

        super().__init__(args)

    def prepare_fake_install(self, fake_install_modules: Sequence[str]) -> None:
        '''
        Prepares the given modules for fake-install into the database.
        :param fake_install_modules: a sequence of module names.
        '''
        fake_install_version: str = '0.1.0.1'
        fake_install_values: str = ', '.join(
            f'(`{module}`, `to upgrade`, `{fake_install_version}`)'
            for module in fake_install_modules
        )
        fake_install_query: str = (
            'INSERT INTO ir_module_module (name, state, latest_version) '
            'VALUES ' + fake_install_values
        )
        logger.info(f'Preparing {len(fake_install_modules)} modules to fake-install')
        # TODO: somehow add fake install to cleanups?
        self.ssh_run(['psql', '-c', fake_install_query])

    def _prepare_upgrade_path_files(self, *sources: str, dest: str, **copy_kwargs):
        dest_noslash: str = dest
        if dest_noslash.endswith(('/', '\\')):
            dest_noslash = dest_noslash[:-1]
        logger.info(f'Preparing `{os.path.basename(dest_noslash)}` upgrade files on SH')
        copy_kwargs.setdefault('to_cleanup', True)
        self.copy_to_sh_branch(*sources, dest=dest, **copy_kwargs)
        self._prepared_upgrade_paths.add(dest_noslash)

    def copy_upgrade_path_files(self) -> None:
        logger.debug(f'Making sure `{self.remote_upgrade_dir}` exists')
        self.ssh_run(['mkdir', '-p', self.remote_upgrade_dir])
        self.paths_to_cleanup.append(self.remote_upgrade_dir)

        self._prepare_upgrade_path_files(
            os.path.join(self.upgrade_repo_path, UPGRADE_UTIL_RELPATH),
            os.path.join(self.psbe_upgrade_repo_path, PSBE_UPGRADE_BASE_RELPATH),
            dest=self.remote_util_path,
            dest_as_dir=True,
        )
        self._prepare_upgrade_path_files(
            os.path.join(self.psbe_upgrade_repo_path, PSBE_MIGRATIONS_RELPATH) + '/',
            dest=self.remote_psbe_upgrade_path,
            dest_as_dir=True,
        )

    @property
    def prepared_upgrade_path(self) -> str:
        return ','.join(self._prepared_upgrade_paths)

    def set_config_upgrade_path(self, upgrade_path: Optional[str]) -> None:
        ssh_result: subprocess.CompletedProcess = self.ssh_run(
            ['cat', REMOTE_ODOO_CONFIG],
            stdout=subprocess.PIPE,
            text=True,
        )
        odoo_config_data: str = ssh_result.stdout
        odoo_config_data_new: str = edit_odoo_config_data(
            odoo_config_data, edit_data={('options', 'upgrade_path'): upgrade_path}
        )
        self.ssh_run(
            f'cat > `{REMOTE_ODOO_CONFIG}`',
            stdin_data=odoo_config_data_new,
            text=True,
        )

    def run_odoo_bin_upgrade(
        self,
        upgrade_path: str,
        install_modules: Sequence[str],
        upgrade_modules: Sequence[str],
    ) -> None:
        odoo_bin_cmdline: List[str] = [
            'odoo-bin',
            '--addons-path=~/src/odoo/addons,~/src/enterprise,~/src/themes,~/src/user',
            '--upgrade-path=' + upgrade_path,
            '--stop-after-init',
        ]
        if install_modules:
            odoo_bin_cmdline += ['-i', ','.join(install_modules)]
        if upgrade_modules:
            odoo_bin_cmdline += ['-u', ','.join(upgrade_modules)]
        logger.info(f'Running modules upgrade')
        self.ssh_run(odoo_bin_cmdline)

    @abstractmethod
    def _run_upgrade(self) -> None:
        '''Run the upgrade'''

    def run(self) -> None:
        self.test_ssh()  # FIXME: move somewhere else like in OdooSH?
        try:
            self._run_upgrade()
        except Exception as exc:
            logger.error(f'Got an exception: {repr(exc)}')
            raise
        else:
            logger.success(f'Upgrade on {self.sh_branch} was successful')
        finally:
            self._cleanup()

    def _cleanup(self):
        if not self.paths_to_cleanup:
            return
        logger.info(f'Cleaning up copied temporary files')
        self.cleanup_copied_files()


class OdooSHUpgradeManualCommand(OdooSHUpgradeBaseCommand):
    '''
    Manually run 'odoo-bin' on SH to install / upgrade the specified modules,
    copying the required 'util' files beforehand.
    Useful to run migrations right after having uploaded a dump on the branch.
    '''

    name = 'upgrade-manual'
    arguments = [
        dict(
            aliases=['-u', '--upgrade'],
            action=CommaSplitAction,
            help='Comma-separated list of modules to upgrade',
        ),
        dict(
            aliases=['-i', '--install'],
            action=CommaSplitAction,
            help='''
            Comma-separated list of new modules to install.
            They will be 'fake-installed' and upgraded, so that eventual migration scripts are run.
            ''',
        ),
    ]

    def __init__(self, args: Namespace):
        super().__init__(args)
        if not args.install and not args.upgrade:
            raise ValueError('Must specify at least one module to install or upgrade')
        self.install_modules: Sequence[str] = args.install or []
        self.upgrade_modules: Sequence[str] = args.upgrade or []

    def _run_upgrade(self) -> None:
        self.copy_upgrade_path_files()

        install_modules: Sequence[str] = self.install_modules
        upgrade_modules: Sequence[str] = self.upgrade_modules
        if install_modules:
            self.prepare_fake_install(install_modules)
            install_modules = []
            upgrade_modules = list({*self.install_modules, *self.upgrade_modules})

        upgrade_path: str = self.prepared_upgrade_path
        self.run_odoo_bin_upgrade(upgrade_path, install_modules, upgrade_modules)

        logger.info(f'Restarting SH server')
        self.ssh_run('odoosh-restart')


@dataclass
class UpgradeBuildContext:
    previous_build_info: Optional[Mapping[str, Any]] = None
    wait_for_build_kwargs: Optional[Mapping[str, Any]] = None
    expected_commit_sha: Optional[str] = None


class OdooSHUpgradeBuildCommand(OdooSHUpgradeBaseCommand):
    '''
    TODO: Missing command description
    '''

    name = 'upgrade-build'
    arguments = [
        dict(
            aliases=['-i', '--install'],
            action=CommaSplitAction,
            help='''
            Comma-separated list of new modules to install.
            They will be 'fake-installed' and upgraded, so that eventual migration scripts are run.
            ''',
        ),
    ]

    def __init__(self, args: Namespace):
        super().__init__(args)
        self.install_modules: Sequence[str] = args.install or []
        self.upgrade_path_config_set: bool = False
        self.previous_build_ssh_url: Optional[str] = None

    @contextmanager
    def upgrade_build_context(self) -> Iterator[UpgradeBuildContext]:
        build_info: Optional[Mapping[str, Any]]
        build_info = self.sh_connector.build_info(self.sh_branch)
        if not build_info:
            raise RuntimeError(f"Couldn't get last build for branch {self.sh_branch}")
        previous_build_commit_id: str = build_info["head_commit_id"][1]

        self.copy_upgrade_path_files()

        if self.install_modules:
            self.prepare_fake_install(self.install_modules)

        logger.info(f'Setting odoo config "upgrade_path"')
        self.set_config_upgrade_path(self.prepared_upgrade_path)
        self.upgrade_path_config_set = True  # TODO: do in the method?

        upgrade_context: UpgradeBuildContext = UpgradeBuildContext(
            previous_build_info=build_info
        )
        yield upgrade_context

        logger.info(f"Waiting for SH to build on new commit")
        new_build_info: Optional[Mapping[str, Any]] = None
        try:
            # TODO: refactor call as callable of the context, wrap yield instead,
            #       this allows to wait for none or more builds, so collect
            #       from the callable the new builds infos to append for cleanup
            new_build_info = self.wait_for_build(
                check_success=True, **(upgrade_context.wait_for_build_kwargs or {})
            )
        except BuildCompleteException as build_exc:
            # get the new failed build for either warning logging or cleanup
            new_build_info = build_exc.build_info
            status_info: Optional[str] = new_build_info.get("status_info")
            if isinstance(build_exc, BuildWarning):
                logger.warning(
                    "SH build completed with warnings"
                    + (f": {status_info}" if status_info else "")
                )
            else:
                raise
        finally:
            if new_build_info:
                expected_sha: Optional[str] = upgrade_context.expected_commit_sha
                new_build_sha: str = new_build_info["head_commit_id"][1]
                if expected_sha and new_build_sha != expected_sha:
                    logger.warning(
                        f"New build has a different commit SHA "
                        f"({new_build_sha}) than expected ({expected_sha})"
                    )
                # set own ssh_url to new build, even if failed
                self.ssh_url = self.sh_connector.get_build_ssh(self.sh_branch, build_id=int(new_build_info["id"]))
            else:
                self.ssh_url = None

            # N.B. the previous build container gets a new id, let's use commit
            previous_build_info: Optional[Mapping[str, Any]]
            previous_build_info = self.sh_connector.build_info(self.sh_branch, commit=previous_build_commit_id)
            if previous_build_info and previous_build_info["status"] != "dropped":
                self.previous_build_ssh_url = self.sh_connector.get_build_ssh(self.sh_branch,
                                                                              build_id=previous_build_info["id"])
            else:
                logger.info(
                    f"Previous build on {previous_build_commit_id[:7]} unavailable, "
                    f"no need to cleanup"
                )

    def _cleanup(self):
        if not self.paths_to_cleanup and not self.upgrade_path_config_set:
            return
        for ssh_url in (self.ssh_url, self.previous_build_ssh_url):
            if ssh_url is None:
                continue
            self.ssh_url = ssh_url  # FIXME: kinda hacky
            logger.info(f'Cleaning up on {ssh_url}')
            if self.upgrade_path_config_set:
                logger.info(f'Removing `upgrade_path` config setting')
                self.set_config_upgrade_path(None)
            super()._cleanup()


class OdooSHUpgradeMergeCommand(OdooSHUpgradeBuildCommand, commands.GitHubCommand):
    '''
    Prepares the SH branch to run automatic upgrades with `util` support for
    merging a PR / pushing commits, and cleans up after it's done.
    Directly handles the PR merge.
    '''

    name = 'upgrade-merge'
    arguments = [
        dict(
            name='pull_request',
            type=int,
            help='Pull request number from the GitHub repository',
        ),
        dict(
            name='merge_method',
            choices=('merge', 'squash', 'rebase'),
            help='Method used to merge the pull request',
        ),
        dict(
            aliases=['-c', '--commit-title'],
            help='Title to use for the commit instead of the automatic one',
        ),
        dict(
            aliases=['-m', '--commit-message'],
            help='Extra message appended to the commit',
        ),
    ]

    def __init__(self, args: Namespace):
        super().__init__(args)

        project_info: Mapping[str, Any]
        [project_info] = self.sh_connector.get_project_info()
        self.repo: Repository = self.github.get_repo(project_info["full_name"])
        self.pull_request: PullRequest = self.repo.get_pull(args.pull_request)
        if self.pull_request.merged or not self.pull_request.mergeable:
            raise RuntimeError(
                f'Pull request {self.repo.full_name} '
                f'#{self.pull_request.number} is not mergeable!'
            )
        pr_dest_branch: str = self.pull_request.base.ref
        if pr_dest_branch != self.sh_branch:
            raise RuntimeError(
                f'Pull request {self.repo.full_name} #{self.pull_request.number} '
                f'destination branch ({pr_dest_branch}) '
                f'is different than the SH one ({self.sh_branch})'
            )

        self.merge_method: str = args.merge_method
        self.commit_title: Optional[str] = args.commit_title
        self.commit_message: Optional[str] = args.commit_message

    def _run_upgrade(self) -> None:
        logger.info(
            f'Will be merging `{self.repo.full_name}` '
            f'PR #{self.pull_request.number} `{self.pull_request.title}` '
            f'and running automatic modules upgrades on the SH branch.\n'
            f'''  - branches: merging `{self.pull_request.head.ref}` into `{self.pull_request.base.ref}`\n'''
            f'''  - merge method: {self.merge_method}\n'''
            f'''  - merge commit title: {self.commit_title or '(automatic)'}\n'''
            f'''  - merge commit message: {self.commit_message or '(automatic)'}\n'''
            f'''  - new modules to (fake-)install: '''
            f'''{', '.join(self.install_modules) if self.install_modules else '(none)'}'''
        )
        logger.warning(
            'The pull-request merge action cannot be undone! '
            'Please check that all the above information is correct'
        )

        if not logger.confirm('Proceed?'):
            raise CommandAborted()

        upgrade_context: UpgradeBuildContext
        with self.upgrade_build_context() as upgrade_context:
            logger.info(
                f'Merging ({self.merge_method}) '
                f'pull request {self.repo.full_name} #{self.pull_request.number}'
            )
            # PyGithub considers None args as intended values, so we need to remove them
            merge_kwargs: MutableMapping[str, Any] = dict(
                merge_method=self.merge_method,
                commit_title=self.commit_title,
                commit_message=self.commit_message,
                sha=self.pull_request.head.sha,
            )
            merge_kwargs = {k: v for k, v in merge_kwargs.items() if v is not None}
            result: PullRequestMergeStatus.PullRequestMergeStatus = self.pull_request.merge(**merge_kwargs)
            if not result.merged:
                raise RuntimeError(
                    f'Pull request {self.repo.full_name} #{self.pull_request.number} '
                    f'did not merge: {result.message}'
                )
            merge_commit_sha: str = result.sha
            upgrade_context.expected_commit_sha = merge_commit_sha


class OdooSHUpgradeWaitCommand(OdooSHUpgradeBuildCommand):
    '''
    Prepares the SH branch to run automatic upgrades with `util` support
    and waits for a new SH build to complete, then cleans up when it's done.
    Useful for handling all other build cases (webhook redeliver, generic push).
    '''

    name = 'upgrade-wait'

    def _run_upgrade(self) -> None:
        context: UpgradeBuildContext
        with self.upgrade_build_context() as context:
            context.wait_for_build_kwargs = dict(build_appear_timeout=600.0)


# TODO: implement variations:
#       upgrade-push      (git push)
#       upgrade-redeliver (redeliver webhook)
