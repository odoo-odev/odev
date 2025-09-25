"""Run unit tests on an empty local Odoo database."""

import re
from collections import defaultdict
from collections.abc import Mapping, MutableMapping
from pathlib import Path
from typing import cast

from odev.common import args, string
from odev.common.commands import OdoobinCommand
from odev.common.console import TableHeader
from odev.common.databases import LocalDatabase
from odev.common.logging import logging
from odev.common.odoobin import OdoobinProcess


logger = logging.getLogger(__name__)


class TestCommand(OdoobinCommand):
    """Run unit tests on an empty local Odoo database, creating it on the fly."""

    _name = "test"
    _aliases = ["tests"]

    tests = args.List(
        aliases=["-t", "--tags"],
        default=[],
        description="""
        Comma-separated list of files or tags to run specific tests.
        Check https://www.odoo.com/documentation/17.0/fr/developer/cli.html#testing-configuration
        for more information on how to use tests.
        """,
    )
    modules = args.List(
        aliases=["-i", "--init"],
        default=["base"],
        description="Comma-separated list of modules to install for testing. If not set, install the base module.",
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.test_files: list[str] = []
        """List of test files to run."""

        self.test_tags: list[str] = []
        """List of test tags to run."""

        for test in self.args.tests:
            append_to = self.test_files if Path(test).is_file() else self.test_tags
            append_to.append(test)

        self.test_database: LocalDatabase = LocalDatabase(self.generate_test_database_name())
        """Test database to create."""

        self.test_buffer: list[str] = []
        """Buffer to store the output of odoo-bin running on the test database."""

        self.last_level = ""

    def generate_test_database_name(self) -> str:
        """Return the name of the test database to use.

        :return: Name of the test database to use.
        :rtype: str
        """
        with self._database.psql() as psql, psql.nocache():
            name = self.__generate_database_name()

            while psql.database_exists(name):
                name = self.__generate_database_name()

            return name

    def __generate_database_name(self) -> str:
        """Return the name of the test database to use.

        :return: Name of the test database to use.
        :rtype: str
        """
        return f"{self._database.name}-{string.suid()}"

    def create_test_database(self):
        """Return the arguments to pass to the create command."""
        args = ["--bare"]

        if self._database.version is not None:
            args.extend(["--version", str(self._database.version)])

        args.append(self.test_database.name)
        self.odev.run_command("create", *args)

    def run_test_database(self):
        """Run the test database."""
        args = ["--stop-after-init", "--test-enable"]

        if self.test_files:
            args.extend(["--test-file", ",".join(self.test_files)])

        if self.test_tags:
            args.extend(["--test-tags", ",".join(self.test_tags)])

        args.extend(["--init", ",".join(self.args.modules)])

        if self.args.odoo_args:
            args.extend(self.args.odoo_args)

        if not self.test_database.exists:
            self.create_test_database()

        odoobin = self.test_database.process or OdoobinProcess(self.test_database)
        odoobin.with_version(self._database.version)
        odoobin.with_edition(self._database.edition)
        odoobin.with_venv(self.venv)
        odoobin.with_worktree(self.worktree)

        odoobin.additional_addons_paths = cast(OdoobinProcess, self.odoobin).additional_addons_paths

        try:
            odoobin.run(args=args, progress=self.odoobin_progress)
            self.print_tests_results()
        except RuntimeError as error:
            if self.test_database.process is not None:
                self.test_database.process.kill(hard=True)
            raise self.error(str(error)) from error

    def odoobin_progress(self, line: str):
        """Handle odoo-bin output and fetch information real-time."""
        if re.match(r"^(i?pu?db)?>+", line):
            raise self.error("Debugger detected in odoo-bin output, remove breakpoints and try again")

        problematic_test_levels = ("warning", "error", "critical")
        match = self._parse_progress_log_line(line)

        if match is None:
            if self.last_level in problematic_test_levels:
                self.test_buffer.append(line)

            color = f"logging.level.{self.last_level}" if self.last_level in problematic_test_levels else "color.black"
            self.print(string.stylize(line, color), highlight=False, soft_wrap=False)
            return

        self.last_level = match.group("level").lower()

        if self.last_level in problematic_test_levels and match.group("database") == self.test_database.name:
            self.test_buffer.append(line)

        self._print_progress_log_line(match)

    def run(self):
        """Run the command."""
        self.run_test_database()

    def cleanup(self):
        """Delete the test database."""
        if self.test_database.exists:
            self.test_database.whitelisted = False
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
            logger.info("No failing tests, congratulations!")
            return

        if self.ODOO_LOG_REGEX.match(self.test_buffer.pop()) is None:
            self.error("Cannot fetch tests results, check the odoo-bin output for more information")
            return

        for test in self.__tests_details():
            self.__print_test_details(test)

        self.print()

    def __tests_details(self) -> list[MutableMapping[str, str]]:
        """Loop through the tests buffer and compile a list of tests information."""
        tests: list[MutableMapping[str, str]] = []
        test: MutableMapping[str, str] = defaultdict(str)
        trace: list[str] = []

        for line in self.test_buffer:
            match = self.ODOO_LOG_REGEX.match(line)

            if match is None:  # This is part of a traceback or a line printed outside of the logger
                trace.append(line)
                continue

            description = str(match.group("description"))

            if re.match(r"^(FAIL|ERROR):\s", description):  # This is the result of a test that failed
                if trace:
                    if tests:
                        tests[-1]["traceback"] = "\n".join(trace)
                    trace.clear()

                test_status, test_identifier = description.split(": ", 1)
                test["status"] = test_status.capitalize()
                test["class"], test["method"] = test_identifier.split(".", 1)
                test["logger"] = match.group("logger")
                module = match.group("module")

                if module is not None:
                    test_path = re.sub(rf"^.*?{module}", module, test["logger"]).replace(".", "/")
                    globs = [p.glob(f"{test_path}.py") for p in self.test_database.process.addons_paths]
                    files = (file for glob in globs for file in glob)
                    test["path"] = cast(Path, next(files, None)).as_posix()
                    test["module"] = module

                tests.append({**test})
                test.clear()

        if tests and trace:
            tests[-1]["traceback"] = "\n".join(trace)
            trace.clear()

        return tests

    def __print_test_details(self, test: Mapping[str, str]):
        """Print the details of a test.

        :param test: The test details.
        """
        self.print()
        self.table(
            [
                TableHeader("Status", style="bold color.red"),
                TableHeader("Class"),
                TableHeader("Method"),
                TableHeader("Module"),
                TableHeader("Path", style="color.black"),
            ],
            [
                [
                    test.get("status", "N/A"),
                    test.get("class", "N/A"),
                    test.get("method", "N/A"),
                    test.get("module", "N/A"),
                    test.get("path", "N/A"),
                ],
            ],
        )

        self.print(string.indent(test["traceback"].rstrip(), 2), style="color.red", highlight=False)
