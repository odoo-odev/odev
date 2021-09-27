# -*- coding: utf-8 -*-

from odev.commands.odoo_bin import run


class ShellCommand(run.RunCommand):
    '''
    Open the Odoo shell for a local database.
    '''

    name = 'shell'
    odoobin_subcommand = 'shell'
