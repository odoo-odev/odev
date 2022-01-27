# -*- coding: utf-8 -*-

import shlex
from argparse import Namespace

from odev.commands.odoo_bin import run
from odev.structures.actions import CommaSplitAction


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
        dict(name='args'),  # moves `args` from RunCommand last
    ]

    def __init__(self, args: Namespace):
        super().__init__(args)

        if TEST_ENABLE not in self.additional_args:
            self.additional_args.append(TEST_ENABLE)

        if args.tags:
            for index, arg in enumerate(self.additional_args):
                if arg.startswith(TEST_TAGS):
                    self.additional_args[index] += f''',{','.join(args.tags)}'''
                    break
            else:
                self.additional_args.append(f'''{TEST_TAGS}={','.join(args.tags)}''')

            if self.force_save_args:
                self.config['databases'].set(
                    self.database,
                    self.config_args_key,
                    shlex.join([*self.addons, *self.additional_args]),
                )


TEST_ENABLE = '--test-enable'
TEST_TAGS = '--test-tags'
