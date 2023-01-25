from typing import List, Optional, Type, Union

from odev.common.commands.base import Command
from odev.common.config import ConfigManager
from odev.common.odev import Odev


def setup_framework() -> Odev:
    """Create a new framework instance."""
    with ConfigManager("odev") as config:
        return Odev(config)


def setup_command_class(command_cls: Type[Command]) -> Type[Command]:
    """Prepare a command (sub)class."""
    command_cls.prepare_command(setup_framework())
    return command_cls


def setup_command(command_cls: Type[Command], arguments: Optional[Union[str, List[str]]] = None):
    """Create a new command instance and parse its arguments."""
    if arguments is None:
        arguments = []

    if isinstance(arguments, str):
        arguments = arguments.split()

    return command_cls(command_cls.parse_arguments(arguments))
