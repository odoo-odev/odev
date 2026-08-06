"""Utility classes and functions for odev."""

from odev.common import bash
from odev.common.config import XGRAM_UNKNOWN
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class EmployeeUtils:
    """Utility class for Odoo employee-related operations."""

    def __init__(self, odev):
        self.odev = odev

    def get_xgram(self) -> str | None:
        """Get the user's xgram from their Odoo email.

        The result is cached in the configuration file: resolving it requires a vault lookup and a call to git,
        which would otherwise be paid on every single odev invocation.
        """
        cached = self.odev.config.user.xgram

        if cached != XGRAM_UNKNOWN:
            return cached or None

        xgram = self._resolve_xgram()
        self.odev.config.user.xgram = xgram or ""

        return xgram

    def _resolve_xgram(self) -> str | None:
        """Resolve the user's xgram from their Odoo email.

        Checks secrets first, then falls back to git configuration.
        """
        # 1. Try from secrets
        try:
            secret = self.odev.store.secrets.get("accounts.odoo.com", ["login"], scope="user", ask_missing=False)
            if secret and secret.login.endswith("@odoo.com"):
                return secret.login.split("@")[0]
        except (AttributeError, KeyError):
            # Ignore missing or malformed secret
            pass
        except Exception:  # noqa: BLE001
            logger.debug("Failed to retrieve xgram from secrets", exc_info=True)

        # 2. Try from git config
        process = bash.execute("git config user.email", raise_on_error=False)
        if process:
            email = process.stdout.decode().strip()
            if email.endswith("@odoo.com"):
                return email.split("@")[0]
        return None

    def is_employee(self) -> bool:
        """Check if the current user is an Odoo employee."""
        return bool(self.get_xgram())
