"""Re-run odev's setup and reconfigure it."""

import inspect
import pkgutil
import textwrap
from importlib.machinery import FileFinder
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import Generator, List, Tuple

from odev.common import commands, string
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class SetupCommand(commands.BaseCommand):
    """Re-run odev's setup and allow reconfiguring parts of it.
    A category can be provided to run a specific part of the setup only.
    """

    name = "setup"
    aliases = ["reconfigure"]
    arguments = [
        {
            "aliases": ["category"],
            "nargs": "?",
            "help": "Run a specific part of the setup only.",
        },
    ]

    def run(self) -> None:
        """Run the setup or part of it."""
        if self.args.category:
            self.run_setup(self.args.category)
        else:
            self.run_setup()

    def run_setup(self, name: str = None) -> None:
        """Run the entire setup."""
        for script in self.__import_setup_scripts():
            if name is None or script.__name__ == name:
                script.setup(self.framework.config)

    @classmethod
    def prepare_command(cls, *args, **kwargs) -> None:
        super().prepare_command(*args, **kwargs)
        scripts: List[Tuple[str, str]] = [
            (script.__name__, string.normalize_indent(script.__doc__)) for script in cls.__import_setup_scripts()
        ]
        script_names = [script[0] for script in scripts]
        cls.update_argument("category", choices=script_names)
        indent = len(max(script_names, key=len))
        description = f"""

            [bold underline]Available categories:[/bold underline]

            {string.format_options_list(scripts, indent_len=indent + 1, blanks=1)}
        """
        cls.description += textwrap.dedent(description).rstrip()

    # --- Private methods ------------------------------------------------------

    @classmethod
    def __import_setup_scripts(cls) -> Generator[ModuleType, None, None]:
        """Import all setup scripts from the setup directory.

        :return: Imported setup modules
        :rtype: Generator[ModuleType]
        """
        setup_modules = pkgutil.iter_modules([d.as_posix() for d in cls.framework.path.glob("odev/setup")])

        for module_info in setup_modules:
            assert isinstance(module_info.module_finder, FileFinder)
            module_path = Path(module_info.module_finder.path) / f"{module_info.name}.py"
            spec = spec_from_file_location(module_path.stem, module_path.as_posix())
            assert spec is not None and spec.loader is not None
            setup_module: ModuleType = module_from_spec(spec)
            spec.loader.exec_module(setup_module)

            if cls.__filter_setup_scripts(setup_module):
                yield setup_module

    @classmethod
    def __filter_setup_scripts(cls, module: ModuleType) -> bool:
        """Filter valid setup scripts.

        :return: Whether the script should be filtered out.
        :rtype: bool
        """
        return inspect.ismodule(module) and hasattr(module, "setup") and callable(module.setup)

    @classmethod
    def __setup_description(cls, script: ModuleType, indent: int = 0) -> str:
        """Return the the description of a setup script.

        :param script: The module of the script to describe.
        :param indent: The number of spaces to indent the description.
        :return: The description of the script.
        :rtype: str
        """
        help_text = textwrap.indent(
            script.__doc__ or "No description available.",
            " " * (indent + 4),
        )[len(script.__name__) :].rstrip()
        return f"{script.__name__}[italic]{help_text}[/italic]"