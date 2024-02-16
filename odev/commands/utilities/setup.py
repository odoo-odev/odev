"""Re-run odev's setup and reconfigure it."""

import inspect
import pkgutil
import textwrap
from importlib.machinery import FileFinder
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import Generator, List, Optional, Tuple

from odev.common import args, string
from odev.common.commands import Command
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class SetupCommand(Command):
    """Re-run odev's setup and allow reconfiguring parts of it.
    A category can be provided to run a specific part of the setup only.
    """

    name = "setup"
    aliases = ["reconfigure"]

    category = args.String(description="Run a specific part of the setup only.", nargs="?")

    def run(self) -> None:
        """Run the setup or part of it."""
        if self.args.category:
            self.run_setup(self.args.category)
        else:
            self.run_setup()

    def run_setup(self, name: Optional[str] = None) -> None:
        """Run the entire setup."""
        for script in self.__import_setup_scripts():
            if name is None or script.__name__ == name:
                script.setup(self.config)

    @classmethod
    def prepare_command(cls, *args, **kwargs) -> None:
        super().prepare_command(*args, **kwargs)
        scripts: List[Tuple[str, str]] = [
            (script.__name__, string.normalize_indent(script.__doc__ or "No description."))
            for script in cls.__import_setup_scripts()
        ]
        script_names = [script[0] for script in scripts]
        cls.update_argument("category", choices=script_names)
        cls.description += textwrap.dedent(
            f"""

            [bold underline]Available categories:[/bold underline]

            {string.format_options_list(scripts, indent_len=len(max(script_names, key=len)) + 1, blanks=1)}
            """
        ).rstrip()

    # --- Private methods ------------------------------------------------------

    @classmethod
    def __import_setup_scripts(cls) -> Generator[ModuleType, None, None]:
        """Import all setup scripts from the setup directory.

        :return: Imported setup modules
        :rtype: Generator[ModuleType]
        """
        setup_modules = pkgutil.iter_modules([d.as_posix() for d in cls._framework.setup_path.parent.glob("setup")])

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
