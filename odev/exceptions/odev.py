"""Odev-related exception classes."""


class OdevException(Exception):
    """Base class for all odev custom exceptions."""


class UpgradeError(OdevException):
    """Raised when  a `odev` upgrade script failed."""
