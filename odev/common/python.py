"""Python and venv-related utilities"""

import re
import shlex
import shutil
import sys
from functools import lru_cache
from pathlib import Path
from subprocess import CompletedProcess
from typing import (
    Callable,
    Generator,
    List,
    Mapping,
    MutableMapping,
    Optional,
    Tuple,
    Union,
    cast,
)

import virtualenv
from cachetools.func import ttl_cache
from packaging.version import Version, parse as parse_version

from odev.common import bash, progress, string
from odev.common.console import console
from odev.common.logging import logging, silence_loggers


__all__ = ["PythonEnv"]


logger = logging.getLogger(__name__)


class PythonEnv:
    """Object representation of a local python environment, this could be the global python interpreter or
    a virtual environment.
    """

    def __init__(self, path: Optional[Union[Path, str]] = None, version: Optional[str] = None):
        """Initializes a python environment.

        :param path: Path to the python environment containing the interpreter to use in the current context.
            If omitted, defaults to the global python interpreter.
        :param version: The python version to use.
            If omitted, defaults to the version of the current python interpreter.
        """
        self._global = path is None
        """Whether the python environment is using the global interpreter (no virtualenv)."""

        path = Path(path or sys.prefix)

        if len(path.parts) == 1:
            from odev.common.odev import HOME_PATH, VENVS_DIRNAME

            path = HOME_PATH / VENVS_DIRNAME / path

        self.path: Path = path.resolve()
        """Path to the current environment."""

        self._version: str = version or (".".join(sys.version.split(".")[:2]))
        """Python version used in the current environment."""

        if not self.exists and self._global:
            raise FileNotFoundError(f"Python interpreter not found at {self.python}")

    def __str__(self) -> str:
        if self._global:
            return "Global Interpreter"

        return f"{self.name} - Python {self.version}" if self.exists else ""

    def __repr__(self) -> str:
        return f"PythonEnv(name={self.name!r}, version={self.version})"

    def __key(self) -> Tuple[str, str, bool]:
        return (self.path.resolve().as_posix(), self._version, self._global)

    def __hash__(self) -> int:
        return hash(self.__key())

    def __eq__(self, __o) -> bool:
        return isinstance(__o, PythonEnv) and __o.__key() == self.__key()

    @property
    def name(self) -> str:
        """The name of the python environment."""
        return "GLOBAL" if self._global else self.path.name

    @property
    def python(self) -> Path:
        """The path to the python interpreter in the current environment."""
        path = self.path / "bin" / "python"

        if not path.exists():
            path = Path(f"{path}{self._version}")

        return path

    @property
    def pip(self) -> str:
        """Base command to run pip in the current environment."""
        return f"{self.python} -m pip"

    @property
    def version(self) -> str:
        """The python version used in the current environment."""
        if self.exists:
            version = self.get_version()
            self._version = version

        return self._version

    @property
    def exists(self) -> bool:
        """Whether the python environment exists."""
        return self.python.is_file()

    @lru_cache
    def get_version(self) -> str:
        """Get the python version used in the current environment."""
        process = bash.execute(f"{self.python} --version")
        assert process is not None
        return ".".join(re.sub(r"[^\d\.]", "", process.stdout.decode()).split(".")[:2])

    def create(self) -> None:
        """Create a new virtual environment."""
        if self._global:
            raise RuntimeError("Cannot create a virtual environment from the global python interpreter")

        venv_description = f"virtual environment {self.name!r} with python version {self.version}"

        with progress.spinner(f"Creating {venv_description}"):
            try:
                with silence_loggers("root", "distlib.util", "filelock"):
                    virtualenv.cli_run(["--python", self.version, self.path.as_posix()], setup_logging=False)
            except RuntimeError as error:
                if str(error).startswith("failed to find interpreter"):
                    logger.critical(
                        f"Missing interpreter for python {self.version}, please install it using your distribution's "
                        "package manager and try again"
                    )
                raise error

        logger.info(f"Created {venv_description}")

    def remove(self) -> None:
        """Remove the current virtual environment."""
        if self._global:
            return logger.error("Cannot remove the global python interpreter")

        venv_description = f"virtual environment {self.name!r}"

        with progress.spinner(f"Removing {venv_description}"):
            shutil.rmtree(self.path, ignore_errors=True)

        logger.info(f"Removed {venv_description}")

    def install_packages(self, packages: List[str]) -> None:
        """Install python packages.
        :param packages: a list of package specs to install.
        """
        self.__pip_install_progress(
            options=" ".join(packages),
            message=f"Installing python packages:\n{string.join_bullet(packages)}",
        )

    def install_requirements(self, path: Union[Path, str]):
        """Install packages from a requirements.txt file.
        :param path: Path to the requirements.txt file or the containing directory.
        """
        requirements_path = self.__check_requirements_path(path)
        self.__pip_install_progress(
            options=f"-r '{requirements_path}'",
            message=f"Installing missing packages from {requirements_path}",
        )

    def __pip_install_progress(self, options: str, message: str = "Installing packages"):
        """Run pip install with a progress spinner.
        :param options: The options to pass to `pip install` (packages or requirements file).
        :param message: The initial message to display in the progress spinner.
        """
        logger.info(message)

        with progress.spinner(message) as spinner:
            re_package = re.compile(r"(?:[\s,](?P<name>[\w_-]+)(?:(?P<op>[<>=]+)(?P<version>[\d.]+))?)")
            buffer: List[str] = []
            packages: List[str] = []

            for line in bash.stream(f"{self.pip} install {options} --no-color"):
                if not line.strip() or line.startswith(" "):
                    buffer.append(line.strip())

                if line.startswith("Collecting"):
                    buffer.clear()
                    match = re_package.search(line)

                    if match is None:
                        continue

                    spinner.update(
                        "Collecting python package "
                        + string.stylize(match.group("name"), "bold color.purple")
                        + f" {match.group('op') or ''} "
                        + string.stylize(match.group("version"), "bold repr.version")
                    )

                elif line.startswith("Building wheels for collected packages:"):
                    buffer.clear()
                    packages = line.replace(",", "").split(" ")[5:]
                    spinner.update(f"Building wheels for {len(packages)} python packages")

                elif line.strip().startswith("Building wheel for"):
                    buffer.clear()
                    package = line.strip().split(" ")[3]
                    spinner.update(f"Building wheels for {len(packages)} python packages ({package})")

                elif line.startswith("Failed to build"):
                    spinner.stop()
                    logger.error("Failed to build python packages:\n" + "\n".join(buffer))
                    break

                elif line.startswith("Installing collected packages:"):
                    buffer.clear()
                    packages = line.replace(",", "").split(" ")[3:]
                    spinner.update(f"Installing {len(packages)} python packages")

                elif line.startswith("Successfully installed"):
                    buffer.clear()
                    packages = line.split(" ")[2:]

        logger.info(f"Successfully installed {len(packages)} python packages")
        installed_packages = [
            f"{string.stylize(name, 'bold color.purple')} == {string.stylize(version, 'bold color.cyan')}"
            for name, version in (package.rsplit("-", 1) for package in packages)
        ]
        logger.debug(f"Installed python packages:\n{string.join_bullet(installed_packages)}")

    @ttl_cache(ttl=60)
    def __pip_freeze_all(self) -> CompletedProcess:
        """Run pip freeze to list all installed packages."""
        packages = bash.execute(f"{self.pip} freeze --all")

        if packages is None:
            raise RuntimeError("Failed to run pip freeze")

        return packages

    def installed_packages(self) -> Mapping[str, Version]:
        """Run pip freeze.

        :return: The result of the pip command execution.
        :rtype: CompletedProcess
        """
        freeze = self.__pip_freeze_all()
        packages = freeze.stdout.decode().splitlines()
        installed: MutableMapping[str, Version] = {}

        for package in packages:
            if "==" in package:
                package_name, package_version = package.split("==")
            elif " @ " in package:
                # ie: odoo_upgrade @ git+https://github.com/odoo/upgrade-util@aaa1f0fee6870075e25cb5e6744e4c589bb32b46
                # git+https://github.com/odoo/upgrade-util is what is in requirements.txt
                _, package_name = package.split(" @ ")
                package_name, _ = package_name.split("@")
                package_version = "1.0.0"
            else:
                raise ValueError(f"Invalid package spec {package}")

            installed[package_name.strip().lower()] = cast(Version, parse_version(package_version.strip()))

        return installed

    def missing_requirements(self, path: Union[Path, str], raise_if_error: bool = True) -> Generator[str, None, None]:
        """Check for missing packages in a requirements.txt file.
        Useful to ensure all packages have the correct version even if the user already installed some packages
        manually.

        :param path: Path to the requirements.txt file or the containing directory.
        :return: A list of missing packages.
        :rtype: List[str]
        """
        try:
            requirements_path = self.__check_requirements_path(path)
        except FileNotFoundError as error:
            if raise_if_error:
                raise error
            return

        logger.debug(f"Checking missing python packages from {requirements_path}")
        installed_packages = self.installed_packages()
        required_packages = requirements_path.read_text().splitlines()
        re_package = re.compile(
            r"""
            (?:
                (?P<name>[\w_-]+)
                (?:
                    (?P<op>[~<>=]+)
                    (?P<version>[\d.*]+)
                )?
                (?:
                    \s*;\s*
                    (?P<conditional>.*)
                )?
            )
            """,
            re.VERBOSE | re.IGNORECASE,
        )

        for line in required_packages:
            line = line.split("#", 1)[0].strip()

            if not line.strip():
                continue

            if "git+" in line:
                package_name, _ = line.split("@")
                installed_version = installed_packages.get(package_name)
                if installed_version is None:
                    logger.debug(f"Missing git python package {package_name}")
                    yield line
                continue

            match = re_package.search(line)

            if match is None:
                continue

            if not self.__check_package_conditions(match.group("conditional")):
                continue

            installed_version = installed_packages.get(match.group("name").lower())

            if installed_version is None:
                logger.debug(f"Missing python package {match.group('name')}")
                yield line
                continue

            if match.group("version") is None and match.group("op") is None:
                continue

            package_operator = match.group("op")

            if package_operator is None:
                continue

            package_version = match.group("version").split("*", 1)[0].rstrip(".")

            version_locals = {
                "installed_version": installed_version,
                "package_version": parse_version(package_version),
            }

            if not eval(f"installed_version {package_operator} package_version", version_locals):
                logger.debug(
                    f"Incorrect python package version {match.group('name')} "
                    f"({installed_version} {package_operator} {package_version})"
                )
                yield line

    def __check_requirements_path(self, path: Union[Path, str]) -> Path:
        requirements_path = Path(path).resolve()

        if requirements_path.is_dir():
            requirements_path = requirements_path / "requirements.txt"

        if not requirements_path.exists():
            raise FileNotFoundError(f"No requirements.txt found under {path}")

        return requirements_path

    def __check_package_conditions(self, conditional: Optional[str]) -> bool:
        if conditional is None:
            return True

        if "python_version" in conditional:
            conditional = re.sub(
                r"(?:'|\")(3.\d+)(?:'|\")",
                lambda m: m.group(1) and " {} ".format(int(m.group(1).replace(".", ""))),
                conditional,
            )

        return eval(
            conditional,
            {
                "sys_platform": sys.platform,
                "python_version": int(self.version.replace(".", "")),
            },
        )

    def run_script(
        self,
        script: Union[Path, str],
        args: Optional[List[str]] = None,
        stream: bool = False,
        progress: Optional[Callable[[str], None]] = None,
        script_input: Optional[str] = None,
    ) -> Optional[CompletedProcess]:
        """Run a python script.

        :param path: Path to the python script to run.
        :param args: A list of arguments to pass to the script.
        :param stream: Whether to stream the output of the script to stdout.
        :param progress: A callback function to call when a line is printed to stdout. Unused if stream is False.
        :param script_input: A string to pass to the script as stdin.
        :return: The result of the script execution.
        :rtype: CompletedProcess
        """
        script_path = Path(script).resolve()
        args = args or []

        if not script_path.exists():
            raise FileNotFoundError(f"Python script not found at {script_path}")

        logger.debug(f"Running python script {script_path}")
        command = f"{self.python} {script_path} {' '.join(args)}"

        if script_input is not None:
            command = f"{script_input} | {command}"

        if not stream:
            return bash.execute(command)

        if progress is None:
            return bash.run(command)

        for line in bash.stream(command):
            progress(line)

        return None

    def run(self, command: str) -> Optional[CompletedProcess]:
        """Run a python command.
        :param command: The command to run.
        :return: The result of the command execution.
        :rtype: CompletedProcess
        """
        command = command.strip()

        if command.startswith("pip"):
            command = f"{self.python} -m {command}"
        elif command.startswith("-"):
            command = f"{self.python} {command}"
        else:
            command = f"{self.python} -c {shlex.quote(command)}"

        logger.info(f"Running {command!r} in virtual environment {self.path.name!r}:")
        console.print()
        return bash.run(command)
