"""SH-related exception classes."""

from typing import Any, List, Mapping, MutableMapping

from odev.exceptions.odev import OdevException


class OdooSHException(OdevException):
    """Base class for SH-related exceptions."""


class BuildException(OdooSHException):  # TODO: Replace with custom exc classes
    """Raised when an exception occurs during a build on Odoo SH."""


class BuildTimeout(BuildException, TimeoutError):
    """Raised when a build on Odoo SH failed due to timeout."""


class BuildCompleteException(BuildException):
    """Raised when a build completed on Odoo SH."""

    def __init__(self, msg: str, *args: List[Any], build_info: Mapping[str, Any], **kwargs: MutableMapping[str, Any]):
        super().__init__(msg, *args, **kwargs)
        self.build_info: Mapping[str, Any] = build_info


class BuildFail(BuildCompleteException):
    """Raised when a build failed on Odoo SH."""


class BuildWarning(BuildCompleteException):
    """Raised when a build on Odoo SH completed with warnings."""


class InvalidBranch(OdooSHException):
    """Raised when the targeted branch is not a git branch or not known from Odoo SH."""


class SHConnectionError(OdooSHException):
    """Raised when an error occurred while trying to fetch an Odoo SH webpage."""


class SHDatabaseTooLarge(OdooSHException):
    """Raised when an Odoo SH db cannot be downloaded because its size exceeds the limit."""
