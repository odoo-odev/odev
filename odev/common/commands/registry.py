"""Registry of the commands odev can run, resolved on demand."""

import json
from collections.abc import Iterator, MutableMapping
from dataclasses import asdict, dataclass, field
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import TYPE_CHECKING, Any

from odev.common.config import CONFIG_DIR
from odev.common.logging import logging


if TYPE_CHECKING:
    from odev.common.commands.base import Command
    from odev.common.odev import Odev


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CommandSource:
    """Module defining a command class, as found on disk."""

    module: str
    """Name the module is imported under."""

    path: str
    """Path to the file defining the command."""

    command_class: str
    """Name of the command class within that module."""


@dataclass
class CommandEntry:
    """What odev knows about a command before importing the module implementing it."""

    name: str
    """Name the command is invoked with."""

    aliases: list[str] = field(default_factory=list)
    """Alternative names the command answers to."""

    help: str = ""
    """Description of the command, as displayed by the help command."""

    sources: list[CommandSource] = field(default_factory=list)
    """Modules defining the command, in registration order: the core one first, then the plugins patching it."""


class CommandRegistry(MutableMapping):
    """Mapping of command names and aliases to the class implementing them.

    A command module imports everything its command needs at module level, so executing all of them only to read
    their names makes every odev invocation pay for every command, plugins included. Names, aliases and help texts
    are therefore cached on disk, and a command module is only executed once that command is actually requested.
    """

    def __init__(self, framework: "Odev"):
        self.framework: Odev = framework
        """Framework the commands are registered against."""

        self.entries: dict[str, CommandEntry] = {}
        """Known commands, by name."""

        self.names: dict[str, str] = {}
        """Name of the command each name and alias refers to."""

        self.classes: dict[str, type[Command]] = {}
        """Command classes that were imported during this run, by command name."""

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({len(self.entries)} commands, {len(self.classes)} imported)"

    # --- Mapping interface ----------------------------------------------------

    def __getitem__(self, name: str) -> type["Command"]:
        command_name = self.names[name]

        if command_name not in self.classes:
            self.classes[command_name] = self.__resolve(self.entries[command_name])

        return self.classes[command_name]

    def __setitem__(self, name: str, command_class: type["Command"]) -> None:
        entry = self.entries.setdefault(command_class._name, CommandEntry(command_class._name))
        entry.aliases = list(command_class._aliases or [])
        entry.help = command_class._help
        self.names[name] = entry.name
        self.classes[entry.name] = command_class

    def __delitem__(self, name: str) -> None:
        command_name = self.names.pop(name)

        if command_name not in self.names.values():
            self.entries.pop(command_name, None)
            self.classes.pop(command_name, None)

    def __iter__(self) -> Iterator[str]:
        return iter(self.names)

    def __len__(self) -> int:
        return len(self.names)

    def clear(self) -> None:
        """Forget every registered command."""
        self.entries.clear()
        self.names.clear()
        self.classes.clear()

    # --- Registration ---------------------------------------------------------

    def register(self, command_class: type["Command"], module_path: Path) -> None:
        """Register a command shipped with odev itself.

        :param command_class: The command class to register.
        :param module_path: Path to the module defining the command class.
        :raise ValueError: If another command already answers to one of its names.
        """
        names = self.__names_of(command_class)

        if any(name in self.names for name in names):
            raise ValueError(f"Another command {command_class._name!r} is already registered")

        logger.debug(f"Registering command {command_class._name!r}")
        source = self.__source_of(command_class, module_path)
        command_class.prepare_command(self.framework)
        self.__store(command_class, names, source)

    def patch(self, command_class: type["Command"], module_path: Path) -> None:
        """Register a command provided by a plugin, letting it patch a command of the same name.

        :param command_class: The command class provided by the plugin.
        :param module_path: Path to the module defining the command class.
        """
        names = self.__names_of(command_class)
        registered = self[command_class._name] if command_class._name in self.names else None
        source = self.__source_of(command_class, module_path)

        if registered is not None and command_class.__bases__ != registered.__bases__:
            logger.debug(f"Patching command {command_class._name!r}")
            command_class = self.__patched(command_class, registered)
        else:
            logger.debug(f"Registering command {command_class._name!r}")

        command_class.prepare_command(self.framework)
        self.__store(command_class, names, source)

    def summaries(self) -> list[CommandEntry]:
        """Describe every registered command without importing any of them.

        :return: The known commands, sorted by name.
        :rtype: List[CommandEntry]
        """
        return sorted(self.entries.values(), key=lambda entry: entry.name)

    # --- On-disk index --------------------------------------------------------

    @property
    def index_path(self) -> Path:
        """Path to the file caching what odev knows about its commands."""
        return CONFIG_DIR / f"{self.framework.name}-commands.json"

    def load(self, fingerprint: Any) -> bool:
        """Restore the command index cached by a previous run.

        :param fingerprint: Signature of the command sources, the index is discarded when it does not match.
        :return: Whether the index could be restored.
        :rtype: bool
        """
        try:
            with self.index_path.open(encoding="utf-8") as index:
                cached = json.load(index)
        except (OSError, json.JSONDecodeError):
            return False

        if cached.get("fingerprint") != fingerprint:
            logger.debug("Command index is out of date, commands will be imported again")
            return False

        self.clear()

        for name, entry in cached["commands"].items():
            self.entries[name] = CommandEntry(
                name=name,
                aliases=entry["aliases"],
                help=entry["help"],
                sources=[CommandSource(**source) for source in entry["sources"]],
            )

            for alias in [name, *entry["aliases"]]:
                self.names[alias] = name

        logger.debug(f"Loaded {len(self.entries)} commands from the index")

        return True

    def save(self, fingerprint: Any) -> None:
        """Cache what odev knows about its commands so the next runs do not have to import them.

        :param fingerprint: Signature of the command sources this index was built from.
        """
        index = {
            "fingerprint": fingerprint,
            "commands": {
                entry.name: {
                    "aliases": entry.aliases,
                    "help": entry.help,
                    "sources": [asdict(source) for source in entry.sources],
                }
                for entry in self.entries.values()
            },
        }

        try:
            self.index_path.parent.mkdir(parents=True, exist_ok=True)

            with self.index_path.open("w", encoding="utf-8") as file:
                json.dump(index, file)
        except OSError as error:
            logger.debug(f"Failed to cache the command index: {error}")

    # --- Private methods ------------------------------------------------------

    def __store(self, command_class: type["Command"], names: list[str], source: CommandSource) -> None:
        """Record a prepared command class and the module it came from.

        :param command_class: The command class to record.
        :param names: Names and aliases the command answers to.
        :param source: Module the command class was defined in, before any patching.
        """
        entry = self.entries.setdefault(command_class._name, CommandEntry(command_class._name))
        entry.aliases = list(command_class._aliases or [])
        entry.help = command_class._help

        if source not in entry.sources:
            entry.sources.append(source)

        for name in names:
            self.names[name] = entry.name

        self.classes[entry.name] = command_class

    def __resolve(self, entry: CommandEntry) -> type["Command"]:
        """Import the modules defining a command and rebuild the class that was registered for it.

        Replaying the sources in the order they were registered in reproduces the patching a plugin applied to a
        command of the same name, without having imported any of the commands that were not asked for.

        :param entry: The command to resolve.
        :return: The command class to run.
        :rtype: Type[Command]
        """
        resolved: type[Command] | None = None

        for source in entry.sources:
            command_class = self.__import(source)

            if resolved is not None and command_class.__bases__ != resolved.__bases__:
                command_class = self.__patched(command_class, resolved)

            command_class.prepare_command(self.framework)
            resolved = command_class

        if resolved is None:
            raise ValueError(f"Command {entry.name!r} has no module to import")

        return resolved

    def __import(self, source: CommandSource) -> type["Command"]:
        """Import the module defining a command and return its class.

        :param source: The module to import.
        :return: The command class it defines.
        :rtype: Type[Command]
        """
        spec = spec_from_file_location(source.module, source.path)

        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load module {source.module} from {source.path}")

        module = module_from_spec(spec)
        spec.loader.exec_module(module)

        return getattr(module, source.command_class)

    @staticmethod
    def __patched(command_class: type["Command"], registered: type["Command"]) -> type["Command"]:
        """Combine a command provided by a plugin with the command it patches.

        :param command_class: The command class provided by the plugin.
        :param registered: The command class already registered under the same name.
        :return: A class inheriting from both.
        :rtype: Type[Command]
        """

        class PatchedCommand(command_class, registered, *registered.__bases__):  # type: ignore [misc, valid-type]
            pass

        PatchedCommand.__name__ = registered.__name__

        return PatchedCommand

    @staticmethod
    def __names_of(command_class: type["Command"]) -> list[str]:
        """List the names and aliases a command answers to."""
        return [command_class._name, *(command_class._aliases or [])]

    @staticmethod
    def __source_of(command_class: type["Command"], module_path: Path) -> CommandSource:
        """Describe where a command class is defined, so that it can be imported again later."""
        return CommandSource(
            module=command_class.__module__,
            path=module_path.as_posix(),
            command_class=command_class.__name__,
        )
