# -*- coding: utf-8 -*-

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


class RunningOdooDatabase(Exception):
    '''
    Raised when trying to access an Odoo database which is currently being used.
    '''
    pass
