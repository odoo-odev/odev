"""Module to manage Odoo processes."""

import re
from functools import lru_cache
from typing import TYPE_CHECKING, Optional

from odev.common import bash


if TYPE_CHECKING:
    from odev.common.databases import PostgresDatabase


class OdooBinProcess:
    """Class to manage an odoo-bin process."""

    def __init__(self, database: "PostgresDatabase"):
        """Initialize the OdooBinProcess object."""
        self.database = database
        self.name = database.name

    @lru_cache
    def _get_ps_process(self) -> Optional[str]:
        """Return the process currently running odoo, if any.
        Grep-ed `ps aux` output.
        """
        process = bash.execute(f"ps aux | grep -E 'odoo-bin\\s+(-d|--database)(\\s+|=){self.name}\\s' || echo -n ''")

        if process is not None:
            return process.stdout.decode()

        return None

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
