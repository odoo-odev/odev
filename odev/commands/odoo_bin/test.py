# -*- coding: utf-8 -*-

import re
from argparse import Namespace

from odev.commands.odoo_bin import run
from odev.structures.actions import CommaSplitAction, OptionalStringAction


class TestCommand(run.RunCommand):
    '''
    Run tests on a local Odoo database.
    '''

    name = 'test'
    arguments = [
        dict(
            name='tags',
            action=CommaSplitAction,
            nargs='?',
            help='''
            Comma-separated list of tags to target specific tests to run
            Check https://www.odoo.com/documentation/14.0/fr/developer/misc/other/cmdline.html
            for more information on test tags
            ''',
        ),
    ]

    def __init__(self, args: Namespace):
        super().__init__(args)

        if TEST_ENABLE not in self.additional_args:
            self.additional_args.append(TEST_ENABLE)

        if args.tags:
            for index in enumerate(filter(lambda a: TEST_TAGS in str(a), self.additional_args)):
                self.additional_args[index] += ',' + args.tags
                break
            else:
                self.additional_args.append(f'''--test-tags={','.join(args.tags)}''')


TEST_ENABLE = '--test-enable'
TEST_TAGS = '--test-tags'
