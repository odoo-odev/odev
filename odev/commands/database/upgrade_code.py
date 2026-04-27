import os
from pathlib import Path
from typing import TYPE_CHECKING

from odev.common import args
from odev.common.commands import OdoobinCommand
from odev.common.logging import logging
from odev.common.version import OdooVersion


if TYPE_CHECKING:
    from odev.common.commands.database import DatabaseType


logger = logging.getLogger(__name__)


class UpgradeCodeCommand(OdoobinCommand):
    """Run Odoo's native upgrade_code tool (Odoo 18.0+).

    This command uses Odoo's internal upgrade_code scripts to automatically
    refactor source code (e.g., renaming <tree> to <list>).
    """

    _name = "upgrade-code"
    _database_arg_required = True

    # Standard Odoo environment arguments
    version_arg = args.String(
        name="version",
        aliases=["-V", "--version"],
        description="The Odoo version to use.",
    )
    venv_arg = args.String(
        name="venv",
        aliases=["--venv"],
        description="Python virtual environment to use.",
    )
    worktree_arg = args.String(
        name="worktree",
        aliases=["-w", "--worktree"],
        description="Git worktree to use.",
    )

    # Upgrade specific flags
    from_version = args.String(
        aliases=["--from"],
        description="Run all scripts starting from this version, inclusive.",
    )
    to_version = args.String(
        aliases=["--to"],
        description="Run all scripts until this version, inclusive.",
    )
    script = args.String(
        aliases=["--script"],
        description="Run this single script name.",
    )
    glob = args.String(
        aliases=["--glob"],
        description="Select the files to rewrite (default: **/*).",
    )
    dry_run = args.Flag(
        aliases=["--dry-run"],
        description="Preview changes without writing.",
    )

    # Catch-all for extra arguments
    odoo_args = args.String(
        nargs="*",
        description="Additional arguments to pass to odoo-bin.",
    )

    def infer_database_instance(self) -> "DatabaseType":
        """Enforce database name and provide helpful error for paths."""
        if self.database_name and (
            "/" in self.database_name or "\\" in self.database_name or "." in self.database_name
        ):
            raise self.error(
                f"Invalid database name: {self.database_name!r}. "
                "odev upgrade-code requires a DATABASE name to resolve the environment context (addons-path, etc.), not a directory path. "
                "Use the designated target database for the upgrade."
            )
        return super().infer_database_instance()

    @property
    def version(self) -> "OdooVersion":
        """Default to target version if specified, as upgrade_code belongs to the target version."""
        if not self.args.version and self.args.to_version:
            return OdooVersion(self.args.to_version)
        return super().version

    def run(self):
        """Run the odoo-bin upgrade_code process."""
        if self.odoobin is None:
            raise self.error(f"No odoo-bin process could be instantiated for version {self.version!r}")

        # odoo-bin upgrade_code is a special CLI that doesn't support --database or --log-level.
        # 1. Subcommand
        cmd_args = ["upgrade_code"]

        # 2. Addons path (resolved from OdoobinProcess)
        addons_path_str = self._prepare_addons_path()
        cmd_args.extend(["--addons-path", addons_path_str])

        # 3. Upgrade specific flags
        self._add_upgrade_flags(cmd_args)

        # 4. Extra arguments & positional path handling
        self._handle_extra_args(cmd_args, addons_path_str)

        # 5. Shell expansion protection
        self._reconstruct_glob_if_expanded(cmd_args)

        # Execute using the virtual environment directly.
        result = self.odoobin.venv.run_script(
            self.odoobin.odoobin_path,
            cmd_args,
            stream=True,
            stream_filter=lambda line: (self.odoobin.console.print(line, end=""), line)[1],
        )
        if result.returncode not in (0, 1):
            raise self.error(f"Odoo exited with code {result.returncode}")

    def _prepare_addons_path(self) -> str:
        """Resolve absolute addon paths."""
        custom_paths = list(dict.fromkeys(p.resolve().as_posix() for p in self.odoobin.addons_paths))
        return ",".join(custom_paths)

    def _add_upgrade_flags(self, cmd_args: list[str]):
        """Append upgrade-specific flags to command arguments."""
        if self.args.script:
            cmd_args.extend(["--script", self.args.script])
        else:
            if self.args.from_version:
                cmd_args.extend(["--from", self.args.from_version])
            if self.args.to_version:
                cmd_args.extend(["--to", self.args.to_version])

        if self.args.glob:
            cmd_args.extend(["--glob", self.args.glob])

        if self.args.dry_run:
            cmd_args.append("--dry-run")

    def _handle_extra_args(self, cmd_args: list[str], addons_path_str: str):
        """Handle additional arguments, detecting directories to add to scan paths."""
        if not self.combined_odoo_args:
            return

        for arg in self.combined_odoo_args:
            path = Path(arg).resolve()
            if path.exists() and path.is_dir():
                if path.as_posix() not in addons_path_str:
                    # Update addons-path argument
                    addons_path_str += f",{path.as_posix()}"
                    try:
                        idx = cmd_args.index("--addons-path") + 1
                        cmd_args[idx] = addons_path_str
                    except (ValueError, IndexError):
                        pass
            elif not (path.exists() and path.is_file()):
                cmd_args.append(arg)

    def _reconstruct_glob_if_expanded(self, cmd_args: list[str]):
        """Reconstruct glob pattern if it was expanded by the shell."""
        potential_glob_files = []
        if self.args.glob and Path(self.args.glob).exists() and Path(self.args.glob).is_file():
            potential_glob_files.append(Path(self.args.glob).resolve())

        for arg in self.combined_odoo_args or []:
            p = Path(arg).resolve()
            if p.exists() and p.is_file():
                potential_glob_files.append(p)

        if len(potential_glob_files) > 1:
            common_parent = Path(os.path.commonpath([f.parent for f in potential_glob_files]))
            for ap in self.odoobin.addons_paths:
                try:
                    rel_parent = common_parent.relative_to(ap.resolve())
                    reconstructed_glob = (rel_parent / "**" / "*").as_posix()
                    self._update_or_append_arg(cmd_args, "--glob", reconstructed_glob)

                    logger.warning(
                        f"Detected shell expansion of your glob pattern. "
                        f'Automatically reconstructed target as --glob "{reconstructed_glob}". '
                        'To avoid this in the future, please quote your glob patterns: --glob "**/*"'
                    )
                    break
                except ValueError:
                    continue

    def _update_or_append_arg(self, cmd_args: list[str], flag: str, value: str):
        """Update existing flag or append it if not found."""
        try:
            idx = cmd_args.index(flag) + 1
            cmd_args[idx] = value
        except (ValueError, IndexError):
            cmd_args.extend([flag, value])
