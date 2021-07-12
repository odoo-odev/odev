"""Runs modules upgrades on a odoo.sh branch with `util` support."""

import logging
import os
from argparse import ArgumentParser, Namespace
from typing import ClassVar, Sequence, List, Optional, Type

from ...cli import CommandType, CommaSplitArgs, CliCommandsSubRoot
from .odoosh import OdooSHBranch, OdooSHSubRoot

__all__ = ["OdooSHUpgrade"]


logger = logging.getLogger(__name__)


# TODO: do proper config
REMOTE_WORK_DIR: str = "/home/odoo/tmp"

UPGRADE_UTIL_RELPATH: str = "migrations/util"
PSBE_MIGRATIONS_RELPATH: str = "migrations"
PSBE_UPGRADE_BASE_RELPATH: str = os.path.join(PSBE_MIGRATIONS_RELPATH, "base")
REMOTE_UTIL_RELPATH: str = "upgrade-util"


class OdooSHUpgrade(OdooSHBranch):
    """
    Command class for running modules upgrades on a odoo.sh branch with `util` support.
    """
    parent: ClassVar[Optional[Type[CliCommandsSubRoot]]] = OdooSHSubRoot
    command: ClassVar[CommandType] = "upgrade"
    help: ClassVar[Optional[str]] = __doc__

    @classmethod
    def prepare_arguments(cls, parser: ArgumentParser) -> None:
        super().prepare_arguments(parser)
        parser.add_argument(
            "--upgrade-repo-path",
            help='the local path of the "upgrade" repo clone from which to copy "util"',
        )
        parser.add_argument(
            "--psbe-upgrade-repo-path",
            help='the local path of the "psbe-custom-upgrade" repo clone '
            'from which "base" and "custom_utils" are copied',
        )
        parser.add_argument(
            "-r",
            "--remote-dir",
            default=REMOTE_WORK_DIR,
            help='remote working dir where files are copied. Defaults to "~/tmp"',
        )
        parser.add_argument(
            "-u",
            "--upgrade",
            action=CommaSplitArgs,
            help="comma-separated list of modules to upgrade",
        )
        parser.add_argument(
            "-i",
            "--install",
            action=CommaSplitArgs,
            help="comma-separated list of new modules to install. "
            'They will be "fake-installed" and upgraded, '
            "so that eventual migration scripts are run.",
        )

    def __init__(self, args: Namespace):
        if args.upgrade_repo_path is None:
            raise ValueError('No "upgrade-repo-path" specified')
        self.upgrade_repo_path: str = os.path.normpath(args.upgrade_repo_path)
        self.psbe_upgrade_repo_path: str = os.path.normpath(args.psbe_upgrade_repo_path)
        self.remote_dir: str = args.remote_dir or REMOTE_WORK_DIR
        if not args.install and not args.upgrade:
            raise ValueError("Must specify at least one module to install or upgrade")
        self.install_modules: Sequence[str] = args.install or []
        self.upgrade_modules: Sequence[str] = args.upgrade or []

        self.remote_util_path: str = os.path.join(self.remote_dir, REMOTE_UTIL_RELPATH)
        self.remote_psbe_upgrade_path: str = os.path.join(
            self.remote_dir, os.path.basename(self.psbe_upgrade_repo_path)
        )
        self.remote_psbe_migrations_path: str = os.path.join(
            self.remote_psbe_upgrade_path, PSBE_MIGRATIONS_RELPATH
        )

        super().__init__(args)

    def prepare_fake_install(self, fake_install_modules: Sequence[str]) -> None:
        """
        Prepares the given modules for fake-install into the database.

        :param fake_install_modules: a sequence of module names.
        """
        fake_install_version: str = "0.1.0.1"
        fake_install_values: str = ", ".join(
            f"('{module}', 'to upgrade', '{fake_install_version}')"
            for module in fake_install_modules
        )
        fake_install_query: str = (
            "INSERT INTO ir_module_module (name, state, latest_version) "
            "VALUES " + fake_install_values
        )
        self.ssh_run(["psql", "-c", fake_install_query])

    def _run_upgrade(self) -> None:
        logger.info('Copying "util" modules to SH branch')
        self.copy_to_sh_branch(
            os.path.join(self.upgrade_repo_path, UPGRADE_UTIL_RELPATH),
            os.path.join(self.psbe_upgrade_repo_path, PSBE_UPGRADE_BASE_RELPATH),
            dest=self.remote_util_path,
            dest_as_dir=True,
        )
        logger.info('Copying "psbe-custom-upgrade" repo to SH branch')
        self.copy_to_sh_branch(
            os.path.join(self.psbe_upgrade_repo_path, PSBE_MIGRATIONS_RELPATH),
            dest=self.remote_psbe_upgrade_path,
            dest_as_dir=True,
        )

        odoo_bin_install_modules: Sequence[str] = self.install_modules
        odoo_bin_upgrade_modules: Sequence[str] = self.upgrade_modules
        fake_install_modules: Sequence[str] = self.install_modules
        if fake_install_modules:
            logger.info(
                f"Preparing {len(fake_install_modules)} modules to fake-install"
            )
            self.prepare_fake_install(fake_install_modules)

            odoo_bin_install_modules = []
            odoo_bin_upgrade_modules = list(
                {*self.install_modules, *self.upgrade_modules}
            )

        upgrade_path: str = ",".join(
            [self.remote_util_path, self.remote_psbe_migrations_path]
        )
        odoo_bin_cmdline: List[str] = [
            "odoo-bin",
            "--addons-path=~/src/odoo/addons,~/src/enterprise,~/src/themes,~/src/user",
            "--upgrade-path=" + upgrade_path,
            "--stop-after-init",
        ]
        if odoo_bin_install_modules:
            odoo_bin_cmdline += ["-i", ",".join(odoo_bin_install_modules)]
        if odoo_bin_upgrade_modules:
            odoo_bin_cmdline += ["-u", ",".join(odoo_bin_upgrade_modules)]
        logger.info(f"Running modules upgrade")
        self.ssh_run(odoo_bin_cmdline)
        logger.info(f"Restarting SH server")
        self.ssh_run("odoosh-restart")

    def run(self) -> None:
        self.test_ssh()
        try:
            self._run_upgrade()
        finally:
            logger.info(f"Cleaning up copied temporary files")
            self.cleanup_copied_files()
