"""Guard the cost odev pays before running the command it was asked to run.

Startup is paid by every single invocation, so an import creeping back into the framework's module graph is a
regression the whole tool feels. Timings are too noisy to assert on, so these tests check the structural cause
instead: what got imported, and when.
"""

import subprocess
import sys
from pathlib import Path
from unittest import TestCase


REPOSITORY_PATH = Path(__file__).parents[3]
"""Path to the odev repository, from which the probed process is started."""

PROBE_MARKER = "ODEV_PROBE:"
"""Prefix identifying the result of a probe among everything odev itself prints."""

PROBE_PREAMBLE = f"""
PROBE = {PROBE_MARKER!r}
import sys
sys.argv = ["odev", "version"]
from odev.common import init_framework
framework = init_framework()
"""
"""Source prepended to every probe, leaving it an initialized but not yet started framework."""

HEAVY_MODULES = (
    "black",
    "copier",
    "github",
    "InquirerPy",
    "networkx",
    "paramiko",
    "prompt_toolkit",
)
"""Third-party modules that are expensive to import and that the framework must not need in order to start.

Each is only useful to a fraction of odev's commands: a GitHub API client, an SSH agent client, a code formatter,
a project scaffolder, a graph library and an interactive prompt toolkit. They belong at their point of use.
"""


class TestStartupPerformance(TestCase):
    """Check that odev does not import what it does not need in order to start."""

    def probe(self, source: str) -> str:
        """Run a snippet in a fresh interpreter and return what it reported.

        A subprocess is required: whatever the test suite itself imported would otherwise pollute the measurement.

        :param source: Python source to run, on top of :data:`PROBE_PREAMBLE`.
        :return: The line the snippet printed, without its marker.
        :rtype: str
        """
        process = subprocess.run(  # noqa: S603
            [sys.executable, "-c", source],
            cwd=REPOSITORY_PATH,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(process.returncode, 0, f"Probe failed:\n{process.stderr}")

        # Odev writes to stdout as well, only the marked line holds the result.
        reported = next((line for line in process.stdout.splitlines() if line.startswith(PROBE_MARKER)), None)
        self.assertIsNotNone(reported, f"Probe did not report anything:\n{process.stdout}\n{process.stderr}")

        return str(reported).removeprefix(PROBE_MARKER)

    def warm_up_command_index(self) -> None:
        """Make sure the commands were already discovered once before measuring.

        The first run of a new version has no index yet and legitimately imports every command to build one. What
        must stay free is every run after it, so give the index a chance to exist first.
        """
        self.probe(f"{PROBE_PREAMBLE}\nframework.start()\nprint(PROBE + 'warmed')\n")

    def test_01_importing_the_framework_stays_lean(self):
        """Importing odev must not pull in the dependencies only a few of its commands need."""
        reported = self.probe(
            f"import odev.common\nimport sys\nprint({PROBE_MARKER!r} + ' '.join("
            f"name for name in {HEAVY_MODULES!r} if name in sys.modules))"
        )
        imported = set(reported.split())

        self.assertEqual(
            imported,
            set(),
            f"Importing odev.common pulled in {', '.join(sorted(imported))}. "
            "Import those where they are used, so that commands that do not need them do not pay for them.",
        )

    def test_02_starting_the_framework_imports_no_command(self):
        """Starting the framework must know every command without executing any of their modules.

        A command module imports whatever its command needs at module level, so importing all of them to discover
        their names makes every invocation pay for every command, plugins included.
        """
        self.warm_up_command_index()

        reported = self.probe(
            f"{PROBE_PREAMBLE}\n"
            "framework.start()\n"
            "print(PROBE + f'{len(framework.commands.entries)} {len(framework.commands.classes)}')\n"
        )
        known, imported = (int(value) for value in reported.split())

        self.assertGreater(known, 0, "The framework did not register any command")
        self.assertEqual(imported, 0, f"Starting the framework imported {imported} command modules, expected none")

    def test_03_running_a_command_imports_only_that_command(self):
        """Resolving a command must import that command alone, not the ones registered alongside it."""
        self.warm_up_command_index()

        reported = self.probe(
            f"{PROBE_PREAMBLE}\n"
            "framework.start()\n"
            "framework.commands['version']\n"
            "print(PROBE + ' '.join(sorted(framework.commands.classes)))\n"
        )

        self.assertEqual(
            reported.split(),
            ["version"],
            f"Resolving the 'version' command imported '{reported.strip()}', expected only 'version'",
        )
