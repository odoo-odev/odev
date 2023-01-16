"""Python and venv-related utilities"""

import sys
import virtualenv
from pathlib import Path
from typing import Union, List, Optional

from odev.common import bash
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class PythonEnv():
    """Object representation of a local python environment, this could be the global python interpreter or
    a virtual environment.
    """

    def __init__(self, path: Optional[Union[Path, str]] = None, version: Optional[float] = None):
        """Initializes a python environment.

        :param path: Path to the python environment containing the interpreter to use in the current context.
            If omitted, defaults to the global python interpreter.
        :param version: The python version to use.
            If omitted, defaults to the version of the current python interpreter.
        """
        self._global = path is None
        self.path: Path = Path(sys.prefix if self._global else path).resolve()
        self.version: float = version or sys.version[:3]
        self.python: Path = self.path / "bin" / f"python{self.version or ''}"
        self.pip: str = f"{self.python} -m pip"

        if not self.python.is_file():
            if self._global:
                raise FileNotFoundError(f"Python interpreter not found at {self.python}")

            self.create_venv(self.path, self.version)

    def create_venv(self) -> None:
        """Create a new virtual environment."""
        if self._global:
            raise RuntimeError("Cannot create a virtual environment from the global python interpreter")

        logger.debug(f"Creating virtual environment at {self.path}")
        virtualenv.cli_run(["--python", self.version, str(self.path)])

    def install_packages(self, packages: List[str]) -> None:
        """Install python packages.

        :param packages: a list of package specs to install.
        """
        logger.debug(f"Installing python packages: {', '.join(packages)}")
        bash.execute(f"{self.pip} install {' '.join(packages)}")

    def install_requirements(self, path: Union[Path, str]) -> None:
        """Install packages from a requirements.txt file.

        :param path: Path to the requirements.txt file or the containing directory.
        """
        requirements_path = Path(path).resolve()

        if requirements_path.is_dir() or requirements_path.name != "requirements.txt":
            requirements_path = requirements_path / "requirements.txt"

        if not requirements_path.exists():
            raise FileNotFoundError(f"No requirements.txt found under in {path}")

        logger.debug(f"Installing python packages from {requirements_path}")
        bash.execute(f'{self.pip} install -r "{requirements_path}"')

    def run_script(self, script: Union[Path, str], args: Optional[List[str]] = None) -> None:
        """Run a python script.

        :param path: Path to the python script to run.
        """
        script_path = Path(script).resolve()
        args = args or []

        if not script_path.exists():
            raise FileNotFoundError(f"Python script not found at {script_path}")

        logger.debug(f"Running python script {script_path}")
        bash.execute(f"{self.python} {script_path} {' '.join(args)}")
