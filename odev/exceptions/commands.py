# -*- coding: utf-8 -*-

class CommandAborted(Exception):
    '''
    Raised when a command has been aborted by the user.
    '''

    def __init__(self, message: str = None, *args, **kwargs) -> None:
        message = message or 'Action cancelled'
        super().__init__(message, *args, **kwargs)


class CommandMissing(Exception):
    '''
    Raised when `odev` is invoked with no command arguments.
    '''
    pass


class InvalidArgument(Exception):
    '''
    Raised when command arguments cannot be parsed or used.
    '''
    pass


class InvalidQuery(Exception):
    '''
    Raised when an error occurred while running SQL queries on a database.
    '''
    pass
