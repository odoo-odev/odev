"""Github-related exception classes."""

from odev.exceptions.odev import OdevException


class GitException(OdevException):
    """Base class for custom git-related exceptions"""


class MissingRemote(GitException):
    """Raised when a repository doesn't have a (specified) remote"""


class MissingTrackingBranch(GitException):
    """Raised when a local branch doesn't have the required tracking branch"""


class HeadRefMismatch(GitException):
    """Raised when HEAD points to a different branch than the specified one"""


class GitEmptyStagingException(GitException):
    """Raised when no files were staged to commit"""
