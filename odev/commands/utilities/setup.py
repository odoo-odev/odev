"""Re-run odev's setup and reconfigure it."""

import inspect
import pkgutil
import textwrap
from collections.abc import Generator
from importlib import import_module
from importlib.util import find_spec
from types import ModuleType
from typing import (
    TYPE_CHECKING,
    cast,
)

from odev.common import args, string
from odev.common.commands import Command
from odev.common.logging import logging


if TYPE_CHECKING:
    from odev.common.odev import Odev


logger = logging.getLogger(__name__)


class SetupCommand(Command):
    """Re-run odev's setup and allow reconfiguring parts of it.
    A category can be provided to run a specific part of the setup only.
    """

    _name = "setup"

    category = args.String(description="Run a specific part of the setup only.", nargs="?")

    def run(self) -> None:
        """Run the setup or part of it."""
        if self.args.category:
            self.run_setup(self.args.category)
        else:
            self.run_setup()

    def run_setup(self, name: str | None = None) -> None:
        """Run the entire setup."""
        package = self.odev.setup_path.relative_to(self.odev.path).as_posix().replace("/", ".")

        for script in self.__import_setup_scripts(package):
            if name is None or script.__name__ == name:
                script.setup(self.odev)

    @classmethod
    def prepare_command(cls, *args, **kwargs) -> None:
        super().prepare_command(*args, **kwargs)

        # During tests, the Odev instance is a patched property and we get the Odev instance back from the class
        # instead of a property object as we would outside tests; I don't like this workaround, but it's the best
        # solution I could come up with...
        odev = cast("Odev", cls.odev.fget(cls) if isinstance(cls.odev, property) and cls.odev.fget else cls.odev)  # type: ignore [attr-defined]
        package = odev.setup_path.relative_to(odev.path).as_posix().replace("/", ".")
        scripts: list[tuple[str, str]] = [
            (script.__name__, string.normalize_indent(script.__doc__ or "No description."))
            for script in cls.__import_setup_scripts(package)
        ]
        script_names = [script[0] for script in scripts]
        cls.update_argument("category", choices=script_names)
        cls._description += textwrap.dedent(
            f"""

            {string.stylize("Available categories:", "bold underline")}

            {string.format_options_list(scripts, indent_len=len(max(script_names, key=len)) + 1, blanks=1)}
            """
        ).rstrip()

    # --- Private methods ------------------------------------------------------

    @classmethod
    def __import_setup_scripts(cls, package: str) -> Generator[ModuleType, None, None]:
        """Import all setup scripts from the setup directory.

        :return: Imported setup modules
        :rtype: Generator[ModuleType]
        """
        loader = find_spec(package)

        if loader is None or loader.submodule_search_locations is None:
            raise ImportError(f"Could not find the setup package {package!r}")

        submodules = sorted(
            (
                import_module(f"{loader.name}.{submodule_info.name}")
                for submodule_info in pkgutil.iter_modules(loader.submodule_search_locations)
            ),
            key=lambda submodule: getattr(submodule, "PRIORITY", 0),
        )

        for submodule in submodules:
            if cls.__filter_setup_scripts(submodule):
                submodule.__name__ = submodule.__name__.removeprefix(f"{package}.")
                yield submodule

    @classmethod
    def __filter_setup_scripts(cls, module: ModuleType) -> bool:
        """Filter valid setup scripts.

        :return: Whether the script should be filtered out.
        :rtype: bool
        """
        return inspect.ismodule(module) and hasattr(module, "setup") and callable(module.setup)
