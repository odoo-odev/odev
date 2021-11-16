'''Gets help about commands.'''

from argparse import ArgumentParser, Namespace, RawTextHelpFormatter
from textwrap import dedent, indent
import sys

from odev.structures import commands
from odev.utils.logging import term


class HelpCommand(commands.Command):
    '''
    Display extensive help about the selected command or a generic help message
    lightly covering all available commands.
    '''

    name = 'help'
    aliases = ['h', 'man', '-h', '--help']
    arguments = [
        dict(
            aliases=['command'],
            nargs='?',
            help='Get help about a specific command',
        ),
    ]

    def run(self):
        '''
        Gets help about commands.
        '''

        registry = getattr(self, 'registry')

        if self.args.command:
            command = registry.get_command([self.args.command])
            parser = ArgumentParser(
                parents=command.prepare_parsers(),
                description=command.help,
                formatter_class=RawTextHelpFormatter,
                add_help=False,
            )

            description = command.help.replace('\n', '\n' + ' ' * 12)
            usage = parser.format_usage().replace('usage:', '').strip().replace(' ', f' {command.name} ', 1)
            title = f'Command: {command.name}'
            message = f'''
            {term.bold(title)}
            {term.snow4('=' * len(title))}

            {description}

            {term.bold('Usage:')}      {usage}
            '''

            if command.aliases:
                aliases = f'''
                {term.bold('Aliases:')}    {', '.join(command.aliases)}
                '''
                message += indent(dedent(aliases), ' ' * 12)

            if parser._positionals:
                arguments = []

                for arg in parser._positionals._group_actions:
                    arg_dict = arg.__dict__
                    arg_help = arg_dict['help'].strip().replace('\n', '\n' + ' ' * 30)
                    arguments.append(f'''{arg_dict['dest']}{' ' * (24 - len(arg_dict['dest']))}{arg_help}''')

                arguments = ('\n' + ' ' * 18).join(arguments)
                positionals = f'''
                {term.bold('Positional Arguments:')}
                  {arguments}
                '''
                message += indent(dedent(positionals), ' ' * 12)

            if parser._optionals:
                arguments = []

                for arg in parser._optionals._group_actions:
                    arg_dict = arg.__dict__
                    arg_options = ', '.join(arg_dict['option_strings'])
                    arg_help = arg_dict['help'].strip().replace('\n', '\n' + ' ' * 30)
                    arguments.append(f'''{arg_options}{' ' * (24 - len(arg_options))}{arg_help}''')

                arguments = ('\n' + ' ' * 18).join(arguments)
                optionals = f'''
                {term.bold('Optional Arguments:')}
                  {arguments}
                '''
                message += indent(dedent(optionals), ' ' * 12)
        else:
            commands = ('\n' + ' ' * 14).join([
                term.bold(c.name) + (' ' * (24 - len(c.name))) + '\n\n' + indent(c.help, ' ' * 16) + '\n'
                for c in sorted(set(registry.commands.values()), key=lambda c: c.name)
            ])

            titles = [
                'ODEV',
                'Automate common tasks relative to working with Odoo development databases',
                'Odev provides the following commands:',
            ]
            message = f'''
            {term.bold(titles[0])} - {term.italic(titles[1])}
            {term.snow4('=' * (len(titles[0] + titles[1]) + 3))}

            Check the complete help on https://github.com/odoo-ps/psbe-ps-tech-tools/tree/odev#readme.

            {term.bold('Usage:')} {sys.argv[0]} <command> <args>

            Arguments in square brackets ({term.italic('[arg]')}) are optional and can be omitted,
            arguments in curvy brackets ({term.italic('{arg}')}) are options to choose from,
            arguments without brackets ({term.italic('arg')}) are required.

            To get help on a specific command and its usage, use {term.italic(f'{sys.argv[0]} help <command>')}

            {term.bold(titles[2])}
            {term.snow4('-' * len(titles[2]))}

              {commands}
            '''

        print(dedent(message).rstrip())

        return 0
