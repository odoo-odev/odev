# -*- coding: utf-8 -*-

from clint.textui import puts, colored

from . import script, dispatcher
from .. import utils

text = """
Automates common tasks relative to working with Odoo development databases.

Check the complete help with examples on https://github.com/odoo-ps/odev#docs.

Arguments in square brackets ([<arg>]) are optional and can be omitted,
arguments in angular brackets (<arg>) are required.

Odev provides the following subcommands:
"""


class HelpScript(script.Script):

    usage = 'help [<command>]'
    alias = ['h']
    args = [['command', 'Optional: command to get extended help for']]
    description = """
Display help about available commands
"""

    def run(self, command, options):
        """
        Display help about available commands.
        """

        if (command):
            if not command in dispatcher.dispatcher:
                utils.log('error', 'Invalid command: %s' % (command))
                return 1
            
            print('%s' % (dispatcher.dispatcher[command].description))
            print('Usage: odev %s\n' % (dispatcher.dispatcher[command].usage))
            
            if dispatcher.dispatcher[command].alias:
                print('Aliases: odev %s\n' % (', odev '.join(dispatcher.dispatcher[command].alias)))

            if dispatcher.dispatcher[command].args:
                print('Arguments:\n')

                for arg in dispatcher.dispatcher[command].args:
                    print('\t%s\t%s' % (arg[0], arg[1]))

        else:
            print(text)

            seen = set()

            for dispatched in dispatcher.dispatcher:
                command = dispatcher.dispatcher[dispatched]

                if command.usage in seen:
                    continue

                seen.add(command.usage)
                print('\todev %s' % (command.usage))
                print('%s' % (command.description.replace('\n', '\n\t\t')))

        return 0
