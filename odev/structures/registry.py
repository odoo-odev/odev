# -*- coding: utf-8 -*-

'''
Commands registry and dispatcher
'''
from packaging import version
import importlib
import os
import sys
import pkgutil
import inspect
from itertools import product
from importlib import import_module
from types import ModuleType
from typing import List, MutableMapping, Optional, Sequence

from odev._version import __version__
from odev.exceptions import CommandMissing, UpgradeError
from odev.utils import logging
from odev.structures.commands import Command, CommandType
from odev.utils.config import ConfigManager


_logger = logging.getLogger(__name__)


class CommandRegistry:
    '''
    Commands registry and dispatcher
    '''

    base_path: str
    '''
    Base path to the directory containing commands.
    '''

    odev_path: str
    '''
    Path to the global odev package.
    '''

    commands: MutableMapping[str, CommandType]
    '''
    Collection of existing and loaded commands.
    '''

    config: ConfigManager
    '''
    Config instance to load the last installed version
    '''

    def __init__(self):
        self.config = ConfigManager('odev')
        self.odev_path = self.config.get('paths', 'odev')
        self.base_path = os.path.join(self.odev_path, 'odev', 'commands')
        self.commands = {}

    def run_upgrades(self):
        current_version = self.config.get('odev', 'version', '0')

        if version.parse(__version__) < version.parse(current_version):
            return

        upgrade_path = os.path.join(self.odev_path, 'odev', "upgrades")
        upgrade_scripts = sorted([x for x in os.listdir(upgrade_path) if os.path.isdir(os.path.join(upgrade_path, x))], key=lambda x: version.Version(x))

        for ver in upgrade_scripts:
            if version.parse(current_version) < version.parse(ver) <= version.parse(__version__):
                for script in sorted(os.listdir(os.path.join(upgrade_path, ver))):
                    name, ext = os.path.splitext(os.path.basename(script))
                    if ext.lower() != '.py':
                        continue

                    _logger.info(f"Running upgrade from {current_version} to {ver}")
                    self.run_upgrade(os.path.join(upgrade_path, ver, script), name)

                self.config.set('odev', 'version', ver)
                current_version = ver

    def run_upgrade(self, path, script):
        spec = importlib.util.spec_from_file_location(script, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        try:
            module.run()
        except Exception as e:
            raise UpgradeError(f"Error while running odev upgrade file {path}") from e

    def load_commands(self):
        '''
        Recursively import commands defined in submodules.
        '''

        directories: List[str] = [self.base_path]

        for rootdir, dirs, _ in os.walk(self.base_path):
            for subdir in dirs:
                if subdir != '__pycache__':
                    directories.append(os.path.join(rootdir, subdir))

        modules = pkgutil.iter_modules(directories)

        def filter_commands(attr):
            return inspect.isclass(attr) \
                and issubclass(attr, Command) \
                and not attr.is_abstract \
                and 'name' in attr.__dict__

        all_commands: List[CommandType] = []

        for pathfinder, module_name, _ in modules:
            if module_name.startswith('__'):
                continue

            package = getattr(pathfinder, 'path').replace(self.odev_path + '/', '').replace('/', '.')
            module: ModuleType = import_module(f'.{module_name}', package=package)
            all_commands += list(filter(filter_commands, module.__dict__.values()))

        for command in all_commands:
            self.register_command(command)

        for subcommand in all_commands:
            self.register_subcommand(subcommand)

        return self

    def register_command(self, command: CommandType):
        '''
        Register a new command and its aliases to the list of available commands.
        '''

        # Ignore subcommands as they are treated differently
        # See: `add_subcommand`
        if command.command:
            return

        command.prepare()
        setattr(command, 'registry', self)
        names = [command.name] + (list(command.aliases) or [])

        for name in names:
            if name in self.commands:
                raise ValueError(f'A command with name `{name}` is already registered')

            self.commands.update({name: command})

    def register_subcommand(self, subcommand: CommandType):
        '''
        Register a new subcommand and its aliases under an existing top-level command.
        '''

        # Ignore top-level commands as they are treated differently
        # See: `add_command`
        if not subcommand.parent:
            return

        subcommand.prepare()
        setattr(subcommand, 'registry', self)
        command: Optional[CommandType] = self.commands.get(subcommand.parent)

        if not command:
            raise ValueError(f'Missing parent command class `{subcommand.parent}` in registry')

        subcommand.command = command
        command_names = [command.name] + (list(command.aliases) or [])
        subcommand_names = [subcommand.name] + (list(subcommand.aliases) or [])

        for names in product(command_names, subcommand_names):
            name = ' '.join(names)

            if name in self.commands:
                raise ValueError(f'A command with name `{name}` is already registered')

            self.commands.update({name: subcommand})
            command.subcommands.update({names[1]: subcommand})

    def get_command(self, argv: Sequence[str]):
        '''
        Find the first applicable command in the registry.
        '''

        if not argv:
            raise CommandMissing('No command specified')

        command_name = argv[0]
        command = self.commands.get(command_name)

        if not command:
            raise CommandMissing(f'No command with name `{command_name}`')

        if command.subcommands and len(argv) > 1:
            subcommand_name = ' '.join(argv[:2])
            subcommand = self.commands.get(subcommand_name)
            return subcommand or command

        return command

    def handle(self, argv: Optional[Sequence[str]] = None) -> int:
        '''
        Handle commands and arguments as received from the terminal.

        :param argv: a list of command line arguments.
            If omitted `sys.argv` will be used instead.
        '''

        argv = argv or sys.argv[1:]
        command_cls = self.get_command(argv)
        parser = command_cls.prepare_parser()

        args = parser.parse_args(argv[1:])
        command = command_cls(args)
        command.argv = argv
        return command.run() or 0
