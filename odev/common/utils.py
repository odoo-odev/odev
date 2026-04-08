"""Utility classes and functions for odev."""

from odev.common import bash


class EmployeeUtils:
    """Utility class for Odoo employee-related operations."""

    def __init__(self, odev):
        self.odev = odev

    def get_xgram(self) -> str | None:
        """Get the user's xgram from their Odoo email.

        Checks secrets first, then falls back to git configuration.
        """
        # 1. Try from secrets
        try:
            secret = self.odev.store.secrets.get("accounts.odoo.com", ["login"], scope="user", ask_missing=False)
            if secret and secret.login.endswith("@odoo.com"):
                return secret.login.split("@")[0]
        except Exception:  # noqa: BLE001, S110
            # Silently ignore secret lookup failures
            pass

        # 2. Try from git config
        try:
            process = bash.execute("git config user.email")
            if process:
                email = process.stdout.decode().strip()
                if email.endswith("@odoo.com"):
                    return email.split("@")[0]
        except Exception:  # noqa: BLE001, S110
            # Silently ignore git config lookup failures
            pass
        return None

    def is_employee(self) -> bool:
        """Check if the current user is an Odoo employee."""
        return bool(self.get_xgram())
