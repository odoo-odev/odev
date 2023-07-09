"""Run unit tests on an empty local Odoo database."""

import re
from collections import defaultdict
from pathlib import Path
from typing import List, Mapping, MutableMapping

from odev.common import string
from odev.common.commands import OdoobinCommand
from odev.common.console import RICH_THEME_LOGGING, Colors
from odev.common.databases import LocalDatabase
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class TestCommand(OdoobinCommand):
    """Run unit tests on an empty local Odoo database, creating it on the fly."""

    name = "test"
    aliases = ["tests"]
    arguments = [
        {
            "name": "tests",
            "action": "store_comma_split",
            "nargs": "?",
            "default": [],
            "help": """
            Comma-separated list of files or tags to run specific tests.
            Check https://www.odoo.com/documentation/16.0/fr/developer/cli.html#testing-configuration
            for more information on how to use tests.
            """,
        },
        {
            "name": "modules",
            "aliases": ["-m", "--modules"],
            "action": "store_comma_split",
            "nargs": "?",
            "default": "all",
            "help": "Comma-separated list of modules to install for testing. If not set, install all modules.",
        },
        {"name": "odoo_args"},
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.test_files: List[str] = []
        """List of test files to run."""

        self.test_tags: List[str] = []
        """List of test tags to run."""

        for test in self.args.tests:
            append_to = self.test_files if Path(test).is_file() else self.test_tags
            append_to.append(test)

        self.test_database: LocalDatabase = LocalDatabase(self.generate_test_database_name())
        """Test database to create."""

        self.test_buffer: List[str] = []
        """Buffer to store the output of odoo-bin running on the test database."""

        self.last_level = ""

    def generate_test_database_name(self) -> str:
        """Return the name of the test database to use.

        :return: Name of the test database to use.
        :rtype: str
        """
        with self.database.psql() as psql:
            name = self.__generate_database_name()

            while psql.database_exists(name):
                name = self.__generate_database_name()

            return name

    def __generate_database_name(self) -> str:
        """Return the name of the test database to use.

        :return: Name of the test database to use.
        :rtype: str
        """
        return f"{self.database.name}_{string.suid()}"

    def create_test_database(self):
        """Return the arguments to pass to the create command."""
        args = ["--bare"]

        if self.database.version is not None:
            args.extend(["--version", str(self.database.version)])

        args.append(self.test_database.name)

        self.odev.run_command("create", *args)

    def run_test_database(self):
        """Run the test database."""
        args = ["--stop-after-init", "--test-enable"]

        if self.test_files:
            args.extend(["--test-file", ",".join(self.test_files)])

        if self.test_tags:
            args.extend(["--test-tags", ",".join(self.test_tags)])

        if self.args.modules:
            args.extend(["--init", ",".join(self.args.modules)])

        if self.args.odoo_args:
            args.extend(self.args.odoo_args)

        assert self.test_database.process
        odoobin = self.test_database.process.with_version(self.database.version)
        odoobin._venv_name = self.database.venv.name
        odoobin.additional_addons_paths = self.odoobin.additional_addons_paths
        odoobin._force_enterprise = self.database.edition == "enterprise"
        self.test_database.whitelisted = False

        try:
            odoobin.run(args=args, progress=self.odoobin_progress)
            self.print_tests_results()
        except RuntimeError as error:
            self.test_database.process.kill(hard=True)
            raise self.error(str(error))

    def odoobin_progress(self, line: str):
        """Handle odoo-bin output and fetch information real-time."""
        if re.match(r"^(i?pu?db)?>+", line):
            raise self.error("Debugger detected in odoo-bin output, remove breakpoints and try again")

        problematic_test_levels = ("warning", "error", "critical")
        match = re.match(self._odoo_log_regex, line)

        if match is None:
            if self.last_level in problematic_test_levels:
                self.test_buffer.append(line)

            color = (
                RICH_THEME_LOGGING[f"logging.level.{self.last_level}"]
                if self.last_level in problematic_test_levels
                else Colors.BLACK
            )
            return self.print(string.stylize(line, color), highlight=False)

        self.last_level = match.group("level").lower()
        level_color = (
            f"bold {Colors.GREEN}"
            if self.last_level == "info"
            else RICH_THEME_LOGGING[f"logging.level.{self.last_level}"]
        )

        if self.last_level in problematic_test_levels:
            self.test_buffer.append(line)

        self.print(
            f"{string.stylize(match.group('time'), Colors.BLACK)} "
            f"{string.stylize(match.group('level'), level_color)} "
            f"{string.stylize(match.group('database'), Colors.PURPLE)} "
            f"{string.stylize(match.group('logger'), Colors.BLACK)}: {match.group('description')}",
            highlight=False,
        )

    def run(self):
        """Run the command."""
        self.create_test_database()
        self.run_test_database()

    def cleanup(self):
        """Delete the test database."""
        if self.test_database.exists:
            self.odev.run_command(
                "delete",
                *[
                    "--force",
                    *["--keep", "venv"],
                    self.test_database.name,
                ],
            )

    def print_tests_results(self):
        """Print the results of the tests."""
        if not self.test_buffer:
            return logger.info("No failing tests, congratulations!")

        if self._odoo_log_regex.match(self.test_buffer.pop()) is None:
            return self.error("Cannot fetch tests results, check the odoo-bin output for more information")

        for test in self.__tests_details():
            self.__print_test_details(test)

        self.print()

    def __tests_details(self):
        """Loop through the tests buffer and compile a list of tests information."""
        tests: List[MutableMapping[str, str]] = []
        test: MutableMapping[str, str] = defaultdict(str)
        trace: List[str] = []

        for line in self.test_buffer:
            match = self._odoo_log_regex.match(line)

            if match is None and tests:  # This is part of a traceback or a line printed outside of the logger
                trace.append(line)
                continue

            description = str(match.group("description"))

            if re.match(r"^(FAIL|ERROR):\s", description):  # This is the result of a test that failed
                test_status, test_identifier = description.split(": ", 1)
                test["status"] = test_status.capitalize()
                test["class"], test["method"] = test_identifier.split(".")
                test["logger"] = match.group("logger")
                module = match.group("module")

                if module is not None:
                    test_path = re.sub(rf"^.*?{module}", module, test["logger"]).replace(".", "/")
                    globs = [p.glob(f"{test_path}.py") for p in self.test_database.process.addons_paths]
                    files = (file for glob in globs for file in glob)
                    test["path"] = next(files, None).as_posix()
                    test["module"] = module

                if trace:
                    test["traceback"] = "\n".join(trace)
                    trace.clear()

                tests.append({**test})
                test.clear()

        return tests

    def __print_test_details(self, test: Mapping[str, str]):
        """Print the details of a test.

        :param test: The test details.
        """
        self.print()
        self.table(
            [
                {"name": "Status", "style": f"bold {Colors.RED}"},
                {"name": "Class"},
                {"name": "Method"},
                {"name": "Module"},
                {"name": "Path", "style": Colors.BLACK},
            ],
            [
                [
                    test["status"],
                    test["class"],
                    test["method"],
                    test["module"],
                    test["path"],
                ],
            ],
        )

        self.print(string.indent(test["traceback"].rstrip(), 2), style=Colors.RED, highlight=False)
