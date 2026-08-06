"""Private namespace owned by a single run of the test suite.

Every resource the suite touches — the datastore database, the databases created by the command tests,
the configuration file, the temporary directories — is named after `SESSION_NAME` or nested under
`SESSION_PATH`. Two suites running at the same time therefore never share anything, and whatever a run
leaves behind can be identified and removed by the next one.

A run holds an exclusive `flock` on its sandbox for its whole lifetime. The kernel releases that lock
when the process dies, whichever way it dies, so a lock that can be taken is proof that its owner is
gone and its leftovers are safe to remove. This is what makes cleanup survive `SIGKILL`, where no
handler of ours can run.
"""

import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from fcntl import LOCK_EX, LOCK_NB, LOCK_UN, flock
from pathlib import Path
from typing import IO

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT, cursor as Cursor

from odev.common.config import CONFIG_DIR
from odev.common.logging import logging
from odev.common.string import suid


logger = logging.getLogger(__name__)


SANDBOX_PREFIX = "odev-test"
"""Prefix shared by every sandbox, and the only namespace this module is ever allowed to delete."""

SANDBOX_ROOT = Path(tempfile.gettempdir())
"""Directory holding the sandbox of each run."""

SESSION_NAME = f"{SANDBOX_PREFIX}-{suid()}"
"""Name of the sandbox owned by this run, used as the name of the odev framework it drives."""

SESSION_PATH = SANDBOX_ROOT / SESSION_NAME
"""Directory holding every file this run creates."""

REAL_CONFIG_DIR = CONFIG_DIR
"""The user's actual configuration directory, captured before the test case redirects `CONFIG_DIR`.

Runs predating this module wrote their `odev-test*` files there; the sweep still cleans them up.
"""

LOCK_NAME = ".lock"
"""Name of the lock file marking a sandbox as owned by a live process."""

MAINTENANCE_DATABASE = "postgres"
"""Database to connect to when listing and dropping the databases of a sandbox."""

SESSION_PARTS = 3
"""Number of dash-separated components in a sandbox name, as in `odev-test-4kq2z81a`."""


_lock: IO[str] | None = None
"""Open handle on this run's lock file, kept for as long as the run lives."""


def acquire() -> None:
    """Create the sandbox of this run and hold its lock until the process exits."""
    global _lock  # noqa: PLW0603 - the lock lives as long as the module does

    if _lock is not None:
        return

    # The sandbox is locked before it is published under its final name, and the rename is atomic: a
    # sweep running in another process must never come across a sandbox that does not hold its lock yet,
    # or it would take it for the leftovers of a dead run and delete it.
    staging = SANDBOX_ROOT / f".{SESSION_NAME}"
    staging.mkdir(parents=True, exist_ok=True)

    _lock = (staging / LOCK_NAME).open("w")
    flock(_lock, LOCK_EX | LOCK_NB)
    staging.rename(SESSION_PATH)


def release() -> None:
    """Remove everything this run created, then release its lock.

    Safe to call more than once: pytest calls it at the end of the session and `atexit` calls it again if
    the interpreter goes down another way.
    """
    global _lock

    if _lock is None:
        return

    handle, _lock = _lock, None

    try:
        discard(SESSION_NAME)
    finally:
        flock(handle, LOCK_UN)
        handle.close()


def sweep() -> None:
    """Remove the sandboxes of runs that no longer hold their lock.

    Covers whatever escaped `release()`: a suite killed with `SIGKILL`, a crashed interpreter, a machine
    that went down mid-run.
    """
    # The sandboxes are listed before the live ones are: a run publishing its own between the two
    # snapshots is then simply absent from the list, rather than present in it and seemingly unowned.
    known = _known_sessions()
    live = _live_sessions()

    for session in sorted(known - live):
        try:
            discard(session)
        except Exception as error:  # noqa: BLE001 - a sandbox we cannot clean must not fail the suite
            logger.warning(f"Could not remove the leftovers of test session {session!r}: {error}")


def discard(session: str) -> None:
    """Remove every trace of a sandbox: its databases, its configuration files and its directory.

    :param session: The name of the sandbox to remove.
    :raises ValueError: If the name falls outside the sandbox namespace.
    """
    if session != SANDBOX_PREFIX and not session.startswith(f"{SANDBOX_PREFIX}-"):
        raise ValueError(f"Refusing to remove {session!r}, which is not a test sandbox")

    # `odev-test` on its own is the sandbox of runs predating this module. Everything below it belongs to
    # other sandboxes, possibly live ones, so only its own name is removed.
    owns_children = session != SANDBOX_PREFIX

    for database in _databases(session, children=owns_children):
        _drop_database(database)

    for path in REAL_CONFIG_DIR.glob(f"{session}*" if owns_children else f"{session}.*"):
        path.unlink(missing_ok=True)

    shutil.rmtree(SANDBOX_ROOT / session, ignore_errors=True)


def _live_sessions() -> set[str]:
    """Return the sandboxes still owned by a running process."""
    return {path.name for path in _sandbox_directories() if _is_locked(path / LOCK_NAME)}


def _known_sessions() -> set[str]:
    """Return every sandbox that left a trace on this machine, live or not."""
    sessions = {path.name for path in _sandbox_directories()}
    sessions |= {_session_of(path.name) for path in REAL_CONFIG_DIR.glob(f"{SANDBOX_PREFIX}*")}
    sessions |= {_session_of(database) for database in _databases(SANDBOX_PREFIX, children=True)}

    return sessions


def _sandbox_directories() -> Iterator[Path]:
    """Yield the sandbox directories present on this machine."""
    return (path for path in SANDBOX_ROOT.glob(f"{SANDBOX_PREFIX}-*") if path.is_dir())


def _is_locked(path: Path) -> bool:
    """Check whether a lock file is held by a live process.

    `flock` conflicts between separate open file descriptions, including within a single process, so this
    also reports the sandbox of the current run as live. A missing lock file means the sandbox predates
    this module or its owner died before taking the lock: either way nobody owns it.
    """
    if not path.exists():
        return False

    try:
        with path.open("r") as handle:
            flock(handle, LOCK_EX | LOCK_NB)
            flock(handle, LOCK_UN)

    except OSError:
        return True

    return False


def _session_of(artifact: str) -> str:
    """Return the sandbox an artifact belongs to.

    Artifacts are named after their sandbox with a suffix of their own, so the sandbox is the first three
    components of the name: the database `odev-test-4kq2z81a-9zf1z0aa` and the file
    `odev-test-4kq2z81a.cfg` both belong to `odev-test-4kq2z81a`. `suid` only ever emits lowercase letters
    and digits, so no component contains a dash of its own.

    :param artifact: The name of a database, or the name of a file including its extension.
    :return: The name of the sandbox owning it.
    :rtype: str
    """
    return "-".join(artifact.split(".")[0].split("-")[:SESSION_PARTS])


def _databases(session: str, children: bool) -> list[str]:
    """List the existing databases belonging to a sandbox.

    :param session: The name of the sandbox.
    :param children: Whether to also return the databases named after a sandbox nested below it.
    :return: The names of the matching databases.
    :rtype: list[str]
    """
    with _maintenance() as cursor:
        if cursor is None:
            return []

        cursor.execute(
            "SELECT datname FROM pg_database WHERE datname = %s OR datname LIKE %s",
            (session, f"{session}-%" if children else session),
        )

        return [name for (name,) in cursor.fetchall()]


def _drop_database(database: str) -> None:
    """Drop a database left behind by a dead run, disconnecting whatever still holds it open."""
    with _maintenance() as cursor:
        if cursor is None:
            return

        cursor.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()",
            (database,),
        )
        cursor.execute(f'DROP DATABASE IF EXISTS "{database}"')


@contextmanager
def _maintenance() -> Iterator[Cursor | None]:
    """Yield a cursor on the maintenance database, or `None` if PostgreSQL cannot be reached.

    Cleaning up is best-effort: a developer without a running PostgreSQL gets a warning rather than a
    suite that refuses to start.
    """
    try:
        connection = psycopg2.connect(database=MAINTENANCE_DATABASE)
    except psycopg2.Error as error:
        logger.warning(f"Could not connect to PostgreSQL to clean up test sandboxes: {error}")
        yield None

        return

    connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

    try:
        yield connection.cursor()
    finally:
        connection.close()
