"""Odoo-related exception classes."""

from typing import Optional

from odev.exceptions.odev import OdevException


class OdooException(OdevException):
    """Base class for odoo-related exceptions."""


class InvalidOdooDatabase(OdooException):
    """Raised when `odev` is invoked on a database with an invalid name."""


class InvalidDatabase(OdooException):
    """Raised when trying to access a non-existing database."""


class InvalidVersion(OdooException):
    """Raised when trying to access a non-existing database."""

    def __init__(self, version: str, msg: Optional[str] = None):
        if not msg:
            msg = "{version} is not a valid Odoo version"
        super().__init__(msg.format(version=version))


class RunningOdooDatabase(OdooException):
    """Raised when trying to access an Odoo database which is currently being used."""


class InvalidOdooModule(OdooException):
    """Raised when a given path is not a valid Odoo module."""


class MissingOdooDependencies(OdooException):
    """Raised when missing dependencies are detected while installing an Odoo module."""
