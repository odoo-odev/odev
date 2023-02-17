"""Python and venv-related utilities"""

import re
import sys
from pathlib import Path
from subprocess import CompletedProcess
from typing import (
    Callable,
    Generator,
    List,
    Mapping,
    Optional,
    Union,
)

import virtualenv
from packaging import version

from odev.common import bash, prompt, style
from odev.common.logging import LOG_LEVEL, logging, silence_loggers


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
        self.path: Path = Path(sys.prefix if self._global else path).resolve()
        self.version: str = version or (".".join(sys.version.split(".")[:2]))
        self.python: Path = self.path / "bin" / f"python{self.version}"
        self.pip: str = f"{self.python} -m pip"

        if not self.exists and self._global:
            raise FileNotFoundError(f"Python interpreter not found at {self.python}")

    def __repr__(self) -> str:
        return f"PythonEnv(name={self.path.name!r}, version={self.version})"

    def create_venv(self) -> None:
        """Create a new virtual environment."""
        if self._global:
            raise RuntimeError("Cannot create a virtual environment from the global python interpreter")

        logger.info(f"Creating virtual environment {self.path.name!r} with python version {self.version}")
        logger.debug(f"Creating virtual environment at {self.path} with python version {self.version}")

        with silence_loggers("root", "distlib.util", "filelock"):
            virtualenv.cli_run(["--python", self.version, self.path.as_posix()], setup_logging=False)

    def install_packages(self, packages: List[str]) -> None:
        """Install python packages.

        :param packages: a list of package specs to install.
        """
        logger.info(f"Installing {len(packages)} python packages")
        logger.debug("Installing python packages:\n" + "\n".join(packages))
        bash.execute(f"{self.pip} install {' '.join(packages)}")

    def install_requirements(self, path: Union[Path, str]):
        """Install packages from a requirements.txt file.

        :param path: Path to the requirements.txt file or the containing directory.
        """
        requirements_path = self.__check_requirements_path(path)
        logger.info(f"Installing python packages from {requirements_path}")
        re_package = re.compile(r"(?:[\s,](?P<name>[\w_-]+)(?:(?P<op>[<>=]+)(?P<version>[\d.]+))?)")
        debug_mode = int(LOG_LEVEL != "DEBUG")

        if debug_mode:
            style.console.print()

        buffer: List[str] = []

        for line in bash.stream(f"{self.pip} install -r '{requirements_path}' --no-color"):
            if not line.strip() or line.startswith(" "):
                buffer.append(line.strip())
                continue

            if line.startswith("Collecting"):
                match = re_package.search(line)

                if match is None:
                    continue

                buffer.clear()
                prompt.clear_line(int(debug_mode))
                logger.info(
                    "Collecting python package "
                    f"[bold {style.PURPLE}]{match.group('name')}[/bold {style.PURPLE}]"
                    f"{match.group('op') or ''}"
                    f"[bold {style.CYAN}]{match.group('version') or ''}[/bold {style.CYAN}]"
                )

            elif line.startswith("Building wheels for collected packages:"):
                buffer.clear()
                prompt.clear_line(int(debug_mode))
                packages = line.replace(",", "").split(" ")[5:]
                logger.debug("Building python packages:\n" + "\n".join(packages))
                logger.info(f"Building wheels for {len(packages)} python packages")

            elif line.startswith("Failed to build"):
                prompt.clear_line(int(debug_mode))
                logger.error("Failed to build python packages:\n" + "\n".join(buffer))
                break

            elif line.startswith("Installing collected packages:"):
                buffer.clear()
                prompt.clear_line(int(debug_mode))
                packages = line.replace(",", "").split(" ")[3:]
                logger.debug("Installing python packages:\n" + "\n".join(packages))
                logger.info(f"Installing {len(packages)} python packages")

            elif line.startswith("Successfully installed"):
                buffer.clear()
                prompt.clear_line(int(debug_mode))
                packages = line.split(" ")[2:]
                logger.debug("Installed python packages:\n" + "\n".join(packages))
                logger.info(f"Successfully installed {len(packages)} python packages")

    def installed_packages(self) -> Mapping[str, version.Version]:
        """Run pip freeze.

        :return: The result of the pip command execution.
        :rtype: CompletedProcess
        """
        logger.debug(f"Running pip freeze in {self.path}")
        result = bash.execute(f"{self.pip} freeze --all")
        packages = result.stdout.decode().splitlines()
        return {package.split("==")[0].lower(): version.parse(package.split("==")[1]) for package in packages}

    def missing_requirements(self, path: Union[Path, str]) -> Generator[str, None, None]:
        """Check for missing packages in a requirements.txt file.
        Useful to ensure all packages have the correct version even if the user already installed some packages
        manually.

        :param path: Path to the requirements.txt file or the containing directory.
        :return: A list of missing packages.
        :rtype: List[str]
        """
        requirements_path = self.__check_requirements_path(path)
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
                "package_version": version.parse(package_version),
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
                lambda m: m.group(1) and str(int(m.group(1).replace(".", ""))),
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
        progress: Callable[[str], None] = None,
    ) -> Optional[CompletedProcess]:
        """Run a python script.

        :param path: Path to the python script to run.
        :param args: A list of arguments to pass to the script.
        :progress: A callback function to call when a line is printed to stdout. Unused if stream is False.
        :return: The result of the script execution.
        :rtype: CompletedProcess
        """
        script_path = Path(script).resolve()
        args = args or []

        if not script_path.exists():
            raise FileNotFoundError(f"Python script not found at {script_path}")

        logger.debug(f"Running python script {script_path}")
        command = f"{self.python} {script_path} {' '.join(args)}"

        if not stream:
            return bash.execute(command)

        if progress is None:
            return bash.run(command)

        progress = progress if progress is not None else style.console.print

        for line in bash.stream(command):
            progress(line)

        return None

    @property
    def exists(self) -> bool:
        """Whether the python environment exists."""
        return self.python.is_file()
