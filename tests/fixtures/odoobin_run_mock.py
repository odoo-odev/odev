"""Helpers to mock Odoo script execution and assert on argv / interpreter paths."""

from __future__ import annotations

import sys
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from odev.common import odev as odev_module
from odev.common.databases import LocalDatabase
from odev.common.python import PythonEnv


TESTS_ROOT = Path(__file__).resolve().parent.parent
FAKE_ODOO_ROOT = (TESTS_ROOT / "resources" / "fake_odoo").resolve()
FAKE_ODOOBIN_PATH = FAKE_ODOO_ROOT / "odoo-bin"


def ensure_fake_venvs() -> None:
    """Symlink bin/python under odev HOME_PATH/virtualenvs/<ver> so versioned venvs exist for tests."""
    home_path = Path(odev_module.HOME_PATH).resolve()
    real_python = Path(sys.executable).resolve()
    for ver in ("18.0", "17.0", "master"):
        bindir = home_path / "virtualenvs" / ver / "bin"
        bindir.mkdir(parents=True, exist_ok=True)
        py = bindir / "python"
        if not py.exists():
            py.symlink_to(real_python)


def stub_minimal_odoo_pg_metadata(database: LocalDatabase, odoo_version: str) -> None:
    """Create minimal ir_module_module rows so LocalDatabase.is_odoo / version work without running odoo-bin."""
    database.query(
        """CREATE TABLE IF NOT EXISTS ir_module_module (
            id SERIAL PRIMARY KEY,
            name VARCHAR,
            latest_version VARCHAR,
            state VARCHAR,
            license VARCHAR
        )"""
    )
    database.query("DELETE FROM ir_module_module WHERE name = 'base'")
    database.query(
        f"INSERT INTO ir_module_module (name, latest_version, state) VALUES ('base', '{odoo_version}', 'installed')"
    )
    database.query(
        """CREATE TABLE IF NOT EXISTS ir_config_parameter (
            id SERIAL PRIMARY KEY,
            key VARCHAR,
            value TEXT
        )"""
    )
    database.query(
        """CREATE TABLE IF NOT EXISTS res_users_log (
            id SERIAL PRIMARY KEY,
            create_date TIMESTAMP
        )"""
    )


def _stdout_for_odoo_argv(argv: list[str]) -> bytes:
    """Minimal stdout so command code paths (e.g. cloc.parse) succeed without a real odoo-bin."""
    if argv and argv[0] == "cloc":
        # Matches ClocCommand.parse: skip first two lines, body lines, last line is total (see re_line_details).
        return b"header1\nheader2\nstub 1 1 1\n 1 1 1\n"
    return b""


def _recording_run_script(  # noqa: PLR0913
    call_log: list, self_pyenv, script, args=None, stream=False, progress=None, script_input=None, **kwargs
):
    script_path = Path(script).resolve()
    argv = list(args or [])
    call_log.append((self_pyenv.python.resolve(), script_path, argv, stream, script_input, kwargs.get("stream_filter")))
    cmd = f"{self_pyenv.python} {script_path} {' '.join(argv)}"
    out = _stdout_for_odoo_argv(argv)
    return CompletedProcess(cmd, 0, out, b"")


def start_run_script_recorder(call_log: list):
    """Patch PythonEnv.run_script to record calls and return success without subprocess."""

    def fake_run_script(  # noqa: PLR0913
        self, script, args=None, stream=False, progress=None, script_input=None, **kwargs
    ):
        return _recording_run_script(call_log, self, script, args, stream, progress, script_input, **kwargs)

    p = patch.object(PythonEnv, "run_script", fake_run_script)
    p.start()
    return p


def iter_odoobin_calls(call_log: list):
    """Yield recorded (python_path, script_path, argv, stream, script_input) for odoo-bin / odoo.py only."""
    for row in call_log:
        name = row[1].name
        if name in ("odoo-bin", "odoo.py"):
            yield row


def assert_argv_contains(test_case, argv: list[str], fragments: list[str], msg: str = ""):
    for frag in fragments:
        test_case.assertIn(frag, argv, msg)


def assert_last_odoobin_invocation(  # noqa: PLR0913
    test_case,
    call_log: list,
    *,
    database_name: str | None = None,
    argv_contains: list[str] | None = None,
    subcommand: str | None = None,
    interpreter_under_virtualenvs: bool = False,
):
    odoos = list(iter_odoobin_calls(call_log))
    test_case.assertTrue(odoos, "expected at least one odoo-bin run_script call")
    _interp, _script, argv, _stream, _inp, _filter = odoos[-1]
    test_case.assertEqual(_script.resolve(), FAKE_ODOOBIN_PATH.resolve())
    interp = _interp.resolve()
    sys_py = Path(sys.executable).resolve()
    if interpreter_under_virtualenvs:
        test_case.assertIn("virtualenvs", interp.as_posix())
    else:
        test_case.assertTrue(
            "virtualenvs" in interp.as_posix() or interp == sys_py,
            f"unexpected interpreter {interp} (expected test venv or {sys_py})",
        )
    if database_name is not None:
        test_case.assertIn("--database", argv)
        idx = argv.index("--database")
        test_case.assertEqual(argv[idx + 1], database_name)
    if subcommand is not None:
        test_case.assertEqual(argv[0], subcommand)
    assert_argv_contains(test_case, argv, argv_contains or [])


def assert_any_odoobin_invocation(
    test_case,
    call_log: list,
    *,
    predicate,
):
    """Assert at least one odoo call matches predicate(argv)."""
    for _i, _s, argv, _st, _in, _f in iter_odoobin_calls(call_log):
        if predicate(argv):
            return
    test_case.fail("no odoo-bin invocation matched predicate")
