# -*- coding: utf-8 -*-

from typing import Optional


class InvalidOdooDatabase(Exception):
    '''
    Raised when `odev` is invoked on a database with an invalid name.
    '''
    pass


class InvalidDatabase(Exception):
    '''
    Raised when trying to access a non-existing database.
    '''
    pass


class InvalidVersion(Exception):
    """Raised when trying to access a non-existing database."""

    def __init__(self, version: str, msg: Optional[str] = None):
        if not msg:
            msg = "{version} is not a valid Odoo version"
        super().__init__(msg.format(version=version))


class RunningOdooDatabase(Exception):
    '''
    Raised when trying to access an Odoo database which is currently being used.
    '''
    pass
