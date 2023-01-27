"""Module to manage Odoo processes."""

import re
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from odev.common import bash
from odev.common.config import ConfigManager
from odev.common.python import PythonEnv
from odev.common.signal_handling import capture_signals
from odev.common.version import OdooVersion


if TYPE_CHECKING:
    from odev.common.databases import PostgresDatabase


class OdooBinProcess:
    """Class to manage an odoo-bin process."""

    def __init__(self, database: "PostgresDatabase", venv: str = None):
        """Initialize the OdooBinProcess object."""
        self.database: PostgresDatabase = database
        """Database this process is for."""

        with self.database:
            self.version: OdooVersion = self.database.exists() and database.odoo_version()
            """Version of Odoo running in this process."""

        with ConfigManager("odev") as config:
            self.odoo_path = Path(config.get("paths", "odoo")).expanduser() / str(self.version)
            """Path to the Odoo installation."""

        self.odoobin_path = self.odoo_path / "odoo/odoo-bin"
        """Path to the odoo-bin executable."""

        self.venv = PythonEnv(self.odoo_path / (venv or "venv"), self._get_python_version())
        """Python virtual environment used by the Odoo installation."""

    @lru_cache
    def _get_ps_process(self) -> Optional[str]:
        """Return the process currently running odoo, if any.
        Grep-ed `ps aux` output.
        """
        process = bash.execute(
            f"ps aux | grep -E 'odoo-bin\\s+(-d|--database)(\\s+|=){self.database.name}\\s*' || echo -n ''"
        )

        if process is not None:
            return process.stdout.decode()

        return None

    def _get_python_version(self) -> Optional[str]:
        """Return the Python version used by the current Odoo installation."""
        if self.version is None:
            return None

        return {
            16: "3.10",
            15: "3.8",
            14: "3.8",
            13: "3.7",
            12: "3.7",
            11: "3.7",
        }.get(self.version.major, "2.7" if self.version.major < 11 else None)

    def _get_odoo_branch(self) -> str:
        """Return the branch of the current Odoo installation."""
        return str(self.version)

    def pid(self) -> Optional[int]:
        """Return the process id of the current database if it is running."""
        process = self._get_ps_process()

        if not process:
            return None

        return int(re.split(r"\s+", process)[1])

    def command(self) -> Optional[str]:
        """Return the command of the process of the current database if it is running."""
        process = self._get_ps_process()

        if not process:
            return None

        return " ".join(re.split(r"\s+", process)[10:])

    def rpc_port(self) -> Optional[int]:
        """Return the RPC port of the process of the current database if it is running."""
        command = self.command()

        if not command:
            return None

        match = re.search(r"(?:-p|--http-port)(?:\s+|=)([0-9]{1,5})", command)
        return int(match.group(1)) if match is not None else 8069

    def is_running(self) -> bool:
        """Return whether Odoo is currently running on the database."""
        return self.pid() is not None

    def kill(self, hard: bool = False):
        """Kill the process of the current database.

        :param hard: Send a SIGKILL instead of a SIGTERM to the running process.
        """
        pid = self.pid()

        if pid is not None:
            bash.execute(f"kill -{9 if hard else 2} {pid}")

    def run(self):
        """Run Odoo on the current database."""
        if self.is_running():
            raise RuntimeError("Odoo is already running on this database.")

        with capture_signals():
            self.venv.run_script(self.odoobin_path, ["-d", self.database.name])
