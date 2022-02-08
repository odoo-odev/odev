# -*- coding: utf-8 -*-

from argparse import Namespace

from odev.constants import PSTOOLS_DB, PSTOOLS_PASSWORD, PSTOOLS_USER
from odev.structures import commands
from odev.utils import logging
from odev.structures import commands, actions


_logger = logging.getLogger(__name__)


class ExportCommand(commands.ExportCommand):
    '''
    Export module from a Odoo db in python or saas
    '''

    name = 'export'
    database_required = False
    exporter_subcommand = 'export'
    arguments = [
        dict(
            aliases=['modules'],
            action=actions.CommaSplitAction,
            nargs='?',
            help='Comma-separated list of modules to export',
        ),
    ]

    def run(self):
        return 0
