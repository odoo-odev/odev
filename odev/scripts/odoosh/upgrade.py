"""Runs modules upgrades on a odoo.sh branch with `util` support."""
import configparser
import logging
import os
import subprocess
from abc import ABC, abstractmethod
from argparse import ArgumentParser, Namespace
from io import StringIO
from typing import (
    ClassVar,
    Sequence,
    List,
    Optional,
    Type,
    Mapping,
    Tuple,
    Set,
)

from ...cli import CommandType, CommaSplitArgs, CliCommandsSubRoot
from .odoosh import OdooSHBranch, OdooSHSubRoot


__all__ = ["OdooSHUpgradeBase", "OdooSHUpgradeManual"]


logger = logging.getLogger(__name__)


# TODO: do proper config
REMOTE_ODOO_HOME: str = "/home/odoo"
REMOTE_ODOO_CONFIG: str = os.path.join(REMOTE_ODOO_HOME, ".config/odoo/odoo.conf")
REMOTE_UPGRADE_DIR: str = os.path.join(REMOTE_ODOO_HOME, "odev-upgrade")

UPGRADE_UTIL_RELPATH: str = "migrations/util"
PSBE_MIGRATIONS_RELPATH: str = "migrations"
PSBE_UPGRADE_BASE_RELPATH: str = os.path.join(PSBE_MIGRATIONS_RELPATH, "base")
REMOTE_UTIL_RELPATH: str = "upgrade-util"


def edit_odoo_config_data(
    config_data: str, edit_data: Mapping[Tuple[Optional[str], str], Optional[str]]
) -> str:
    # preserve comments (although w/out empty lines)
    parser: configparser.ConfigParser = configparser.RawConfigParser(
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


class OdooSHUpgradeBase(OdooSHBranch, ABC):
    """
    Command class for running modules upgrades on a odoo.sh branch with `util` support.
    """

    parent: ClassVar[Optional[Type[CliCommandsSubRoot]]] = OdooSHSubRoot

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
            default=REMOTE_UPGRADE_DIR,
            help='remote working dir where files are copied. Defaults to "~/tmp"',
        )

    def __init__(self, args: Namespace):
        if args.upgrade_repo_path is None:
            raise ValueError('No "upgrade-repo-path" specified')
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
        logger.info(f"Preparing {len(fake_install_modules)} modules to fake-install")
        # TODO: somehow add fake install to cleanups?
        self.ssh_run(["psql", "-c", fake_install_query])

    def _prepare_upgrade_path_files(self, *sources: str, dest: str, **copy_kwargs):
        dest_noslash: str = dest
        if dest_noslash.endswith(("/", "\\")):
            dest_noslash = dest_noslash[:-1]
        logger.info(f'Preparing "{os.path.basename(dest_noslash)}" repo to SH branch')
        self.copy_to_sh_branch(*sources, dest=dest, **copy_kwargs)
        self._prepared_upgrade_paths.add(dest_noslash)

    def copy_upgrade_path_files(self) -> None:
        logger.debug(f'Making sure "{self.remote_upgrade_dir}" exists')
        self.ssh_run(["mkdir", "-p", self.remote_upgrade_dir])
        self.paths_to_cleanup.append(self.remote_upgrade_dir)

        logger.info('Copying "util" modules to SH branch')
        self._prepare_upgrade_path_files(
            os.path.join(self.upgrade_repo_path, UPGRADE_UTIL_RELPATH),
            os.path.join(self.psbe_upgrade_repo_path, PSBE_UPGRADE_BASE_RELPATH),
            dest=self.remote_util_path,
            dest_as_dir=True,
        )
        logger.info('Copying "psbe-custom-upgrade" repo to SH branch')
        self._prepare_upgrade_path_files(
            os.path.join(self.psbe_upgrade_repo_path, PSBE_MIGRATIONS_RELPATH),
            dest=self.remote_psbe_upgrade_path,
            dest_as_dir=True,
        )

    @property
    def prepared_upgrade_path(self) -> str:
        return ",".join(self._prepared_upgrade_paths)

    def set_config_upgrade_path(self, upgrade_path: Optional[str]) -> None:
        ssh_result: subprocess.CompletedProcess = self.ssh_run(
            ["cat", REMOTE_ODOO_CONFIG],
            stdout=subprocess.PIPE,
            text=True,
        )
        odoo_config_data: str = ssh_result.stdout
        odoo_config_data_new: str = edit_odoo_config_data(
            odoo_config_data, edit_data={("options", "upgrade_path"): upgrade_path}
        )
        self.ssh_run(
            f'cat > "{REMOTE_ODOO_CONFIG}"',
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
            "odoo-bin",
            "--addons-path=~/src/odoo/addons,~/src/enterprise,~/src/themes,~/src/user",
            "--upgrade-path=" + upgrade_path,
            "--stop-after-init",
        ]
        if install_modules:
            odoo_bin_cmdline += ["-i", ",".join(install_modules)]
        if upgrade_modules:
            odoo_bin_cmdline += ["-u", ",".join(upgrade_modules)]
        logger.info(f"Running modules upgrade")
        self.ssh_run(odoo_bin_cmdline)

    @abstractmethod
    def _run_upgrade(self) -> None:
        """Run the upgrade"""

    def run(self) -> None:
        self.test_ssh()
        try:
            self._run_upgrade()
        except Exception as exc:
            logger.error(f"Got an exception: {repr(exc)}")
            raise
        finally:
            self._cleanup()

    def _cleanup(self):
        logger.info(f"Cleaning up copied temporary files")
        self.cleanup_copied_files()


class OdooSHUpgradeManual(OdooSHUpgradeBase):
    command: ClassVar[CommandType] = "upgrade-manual"
    help: ClassVar[Optional[str]] = """
        Manually runs "odoo-bin" on SH to install / upgrade the specified modules,
        copying the required "util" files beforehand.
        Useful to run migrations right after having uploaded a dump on the branch.
    """
    help_short: ClassVar[Optional[str]] = help

    @classmethod
    def prepare_arguments(cls, parser: ArgumentParser) -> None:
        super().prepare_arguments(parser)
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
            help="""
                comma-separated list of new modules to install. 
                They will be "fake-installed" and upgraded, 
                so that eventual migration scripts are run.
            """,
        )

    def __init__(self, args: Namespace):
        super().__init__(args)
        if not args.install and not args.upgrade:
            raise ValueError("Must specify at least one module to install or upgrade")
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

        logger.info(f"Restarting SH server")
        self.ssh_run("odoosh-restart")