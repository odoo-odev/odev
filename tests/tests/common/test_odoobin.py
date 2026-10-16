import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from odev.common import string
from odev.common.commands.odoobin import OdoobinCommand
from odev.common.databases import Repository
from odev.common.odoobin import OdoobinProcess

from tests.fixtures import OdevTestCase


class FakeDatabase:
    """Minimal stand-in for a database, exposing only what the addons paths derivation reads."""

    def __init__(self, repository: Repository | None = None):
        self.repository = repository


class TestExpandAddonsPaths(OdevTestCase):
    """`expand_addons_paths` resolves a directory to the addons directories it contains."""

    @property
    def addons_path(self) -> Path:
        return self.res_path / "repositories" / "test" / "test-addons"

    def test_finds_modules_nested_in_subdirectories(self):
        expanded = OdoobinProcess.expand_addons_paths([self.addons_path])
        self.assertEqual(expanded, [self.addons_path, self.addons_path / "submodule"])

    def test_ignores_directories_without_modules(self):
        empty = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, empty, ignore_errors=True)
        self.assertEqual(OdoobinProcess.expand_addons_paths([empty]), [])

    def test_deduplicates_overlapping_inputs(self):
        expanded = OdoobinProcess.expand_addons_paths([self.addons_path, self.addons_path / "submodule"])
        self.assertEqual(expanded, [self.addons_path, self.addons_path / "submodule"])

    def test_no_paths_yields_no_addons_paths(self):
        self.assertEqual(OdoobinProcess.expand_addons_paths([]), [])


class TestAdditionalAddonsPaths(OdevTestCase):
    """The addons paths derived from the linked repository must be expanded, and derived only once."""

    def setUp(self):
        super().setUp()
        self.odev.config.paths.repositories = self.res_path / "repositories"
        self.addons_path = self.res_path / "repositories" / "test" / "test-addons"

    def make_process(self, repository: Repository | None = None) -> OdoobinProcess:
        process = OdoobinProcess.__new__(OdoobinProcess)
        process.database = FakeDatabase(repository)  # type: ignore [assignment]
        process._additional_addons_paths = None
        return process

    def test_repository_is_expanded_to_its_addons_directories(self):
        """Regression for #98: the bare repository root is not a valid addons path when the
        modules live in subdirectories, so it must be expanded before being used.
        """
        process = self.make_process(Repository("test-addons", "test"))
        self.assertEqual(process.additional_addons_paths, [self.addons_path, self.addons_path / "submodule"])

    def test_without_repository_no_addons_paths(self):
        self.assertEqual(self.make_process().additional_addons_paths, [])

    def test_derived_only_once(self):
        process = self.make_process(Repository("test-addons", "test"))
        calls: list[object] = []
        original = OdoobinProcess.expand_addons_paths

        def counting_expand(paths):
            calls.append(paths)
            return original(paths)

        with self.patch(OdoobinProcess, "expand_addons_paths", side_effect=counting_expand):
            for _ in range(3):
                _ = process.additional_addons_paths

        self.assertEqual(len(calls), 1)

    def test_explicit_assignment_is_not_overridden(self):
        process = self.make_process(Repository("test-addons", "test"))
        process.additional_addons_paths = []
        self.assertEqual(process.additional_addons_paths, [])


class EditionDatabase:
    """Minimal stand-in for a database, exposing only the edition installed in it."""

    def __init__(self, edition: str):
        self.edition = edition


class TestForcedEdition(OdevTestCase):
    """`with_edition` forces the edition both ways, regardless of the one installed in the database."""

    def make_process(self, edition: str) -> OdoobinProcess:
        process = OdoobinProcess.__new__(OdoobinProcess)
        process.database = EditionDatabase(edition)  # type: ignore [assignment]
        process._forced_edition = None
        return process

    def repository_names(self, process: OdoobinProcess) -> list[str]:
        return [repository.name for repository in process.odoo_repositories]

    def test_defaults_to_the_database_edition(self):
        self.assertIn("odoo/enterprise", self.repository_names(self.make_process("enterprise")))
        self.assertNotIn("odoo/enterprise", self.repository_names(self.make_process("community")))

    def test_community_forced_on_an_enterprise_database(self):
        process = self.make_process("enterprise").with_edition("community")
        self.assertNotIn("odoo/enterprise", self.repository_names(process))

    def test_enterprise_forced_on_a_community_database(self):
        process = self.make_process("community").with_edition("enterprise")
        self.assertIn("odoo/enterprise", self.repository_names(process))


class LogFormatCommand(OdoobinCommand):
    """Concrete odoo-bin command, only used to reach the log formatting methods."""

    def run(self):
        pass


class TestWerkzeugLogFormat(OdevTestCase):
    """Werkzeug request lines are pretty-printed with or without the query stats Odoo appends to them."""

    LOG_PREFIX = "2026-10-16 09:18:02,123 4242 INFO db werkzeug: 127.0.0.1 - - [16/Oct/2026 09:18:02] "

    def setUp(self):
        super().setUp()
        self.printed: list[str] = []
        self.command = LogFormatCommand.__new__(LogFormatCommand)
        self.command.args = SimpleNamespace(pretty=True)  # type: ignore [assignment]
        print_patch = patch.object(
            self.command, "print", side_effect=lambda renderable, **_: self.printed.append(renderable)
        )
        print_patch.start()
        self.addCleanup(print_patch.stop)

    def format_request(self, request: str) -> str:
        self.command.odoobin_progress(self.LOG_PREFIX + request)

        return self.printed[-1]

    def assert_request_without_timings(self, formatted: str, request: str, code: str) -> None:
        self.assertTrue(formatted.endswith(f"{request} ({code})"), formatted)
        self.assertNotIn("SQL:", formatted)
        self.assertNotIn("Python:", formatted)

    def test_request_with_stats_shows_timings(self):
        # Exact markup on purpose: lines with stats must print as they did before stats became optional.
        self.assertEqual(
            self.format_request('"GET /web/login HTTP/1.1" 200 - 262 0.105 0.303'),
            "[dim]09:18:02,123[/dim] [bold #98c379]INFO[/bold #98c379] [#af5faf]db[/#af5faf] [dim]werkzeug[/dim]: "
            "[dim]127.0.0.1[/dim] [dim]-[/dim] GET /web/login ([dim]200[/dim]) [dim]-[/dim] "
            "[#d19a66]0.408[/#d19a66] [dim][SQL: 0.105 (262 queries), Python: [#d19a66 dim]0.303[/#d19a66 dim]][/dim]",
        )

    def test_request_without_stats_omits_timings(self):
        formatted = self.format_request('"GET /web/static/src/img/favicon.ico HTTP/1.1" 200 - - - -')
        self.assert_request_without_timings(
            formatted, "GET /web/static/src/img/favicon.ico", string.stylize("200", "color.black")
        )

    def test_not_found_without_stats_omits_timings(self):
        formatted = self.format_request('"GET /web/missing HTTP/1.1" 404 - - - -')
        self.assert_request_without_timings(formatted, "GET /web/missing", string.stylize("404", "color.yellow"))

    def test_server_error_without_stats_omits_timings(self):
        formatted = self.format_request('"POST /web/dataset/call_kw HTTP/1.1" 500 - - - -')
        self.assert_request_without_timings(formatted, "POST /web/dataset/call_kw", string.stylize("500", "color.red"))

    def test_no_pretty_prints_raw_line(self):
        line = self.LOG_PREFIX + '"GET /web/static/src/img/favicon.ico HTTP/1.1" 200 - - - -'
        self.command.args = SimpleNamespace(pretty=False)  # type: ignore [assignment]
        self.command.odoobin_progress(line)

        self.assertEqual(self.printed, [line])
