# -*- coding: utf-8 -*-

from typing import Mapping, Any


class BuildException(RuntimeError):  # TODO: Replace with custom exc classes
    '''
    Raised when an exception occurs during a build on Odoo SH.
    '''
    pass


class BuildTimeout(BuildException, TimeoutError):
    '''
    Raised when a build on Odoo SH failed due to timeout.
    '''
    pass


class BuildCompleteException(BuildException):
    '''
    Raised when a build completed on Odoo SH.
    '''
    def __init__(self, *args, build_info: Mapping[str, Any], **kwargs):
        super().__init__(*args, **kwargs)
        self.build_info: Mapping[str, Any] = build_info


class BuildFail(BuildCompleteException):
    '''
    Raised when a build failed on Odoo SH.
    '''
    pass


class BuildWarning(BuildCompleteException):
    '''
    Raised when a build on Odoo SH completed with warnings.
    '''
    pass


class InvalidBranch(Exception):
    '''
    Raised when the targeted branch is not a git branch or not known from Odoo SH.
    '''
    pass


class SHConnectionError(Exception):
    '''
    Raised when an error ocurred while trying to fetch an Odoo SH webpage.
    '''
    pass


class SHDatabaseTooLarge(Exception):
    '''
    Raised when an Odoo SH database cannot be downloaded because its size exceed the limit.
    '''
    pass
