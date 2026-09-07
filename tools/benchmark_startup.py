#!/usr/bin/env python3
"""Measure how long odev takes to start up and shut down.

Every odev invocation pays the framework's startup cost before the command it was asked to run even begins, and
pays an exit cost after that command printed its result. Both are directly perceptible for a tool run dozens of
times a day, so this script reports them separately instead of a single wall-clock number.

Usage:
    ~/.config/odev/venv/bin/python tools/benchmark_startup.py [--runs N] [--command NAME]
"""

import argparse
import statistics
import subprocess
import sys
import time
from pathlib import Path


REPOSITORY_PATH = Path(__file__).parents[1]
"""Path to the odev repository, from which the measured process is started."""

HEAVY_MODULES = ("copier", "networkx", "black", "github", "paramiko", "InquirerPy", "prompt_toolkit")
"""Third-party modules that are expensive to import and that a trivial command has no reason to load."""

PHASES_PROBE = """
import sys
from time import monotonic

start = monotonic()
from odev.common import init_framework
imported = monotonic()

odev = init_framework()
odev.start(start)
started = monotonic()

odev.dispatch()
dispatched = monotonic()

heavy = [module for module in {heavy!r} if module in sys.modules]
print(
    f"PROBE {{imported - start}} {{started - imported}} {{dispatched - started}} {{len(sys.modules)}} {{','.join(heavy)}}",
    file=sys.stderr,
)
"""


def measure_process(command: str) -> tuple[float, float]:
    """Run odev in a subprocess and measure its total duration and its exit tail.

    The exit tail is the time between the last byte the command wrote and the moment the process actually died: it
    covers everything odev still does once the user can already read the result.

    :param command: Name of the odev command to run.
    :return: The total duration and the exit tail, both in seconds.
    :rtype: Tuple[float, float]
    """
    start = time.monotonic()
    process = subprocess.Popen(  # noqa: S603
        [sys.executable, "main.py", command],
        cwd=REPOSITORY_PATH,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    last_output = start

    for _ in process.stdout:  # type: ignore [union-attr]
        last_output = time.monotonic()

    process.wait()
    end = time.monotonic()

    return end - start, end - last_output


def measure_phases(command: str) -> tuple[list[float], int, list[str]]:
    """Measure the duration of each startup phase from inside the process.

    :param command: Name of the odev command to run.
    :return: The duration of the import, start and dispatch phases, the number of imported modules and the heavy
        modules that were loaded.
    :rtype: Tuple[List[float], int, List[str]]
    """
    probe = PHASES_PROBE.format(heavy=list(HEAVY_MODULES))
    process = subprocess.run(  # noqa: S603
        [sys.executable, "-c", probe, command],
        cwd=REPOSITORY_PATH,
        capture_output=True,
        text=True,
        check=False,
    )

    line = next((line for line in process.stderr.splitlines() if line.startswith("PROBE ")), None)

    if line is None:
        raise RuntimeError(f"Probe did not report any timing:\n{process.stderr}")

    _, imports, start, dispatch, modules, heavy = line.split(" ")

    return [float(imports), float(start), float(dispatch)], int(modules), [name for name in heavy.split(",") if name]


def main() -> int:
    """Run the benchmark and print its report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=10, help="Number of times the command is run (default: 10)")
    parser.add_argument("--command", default="version", help="Odev command to measure (default: version)")
    arguments = parser.parse_args()

    print(f"Measuring 'odev {arguments.command}' over {arguments.runs} runs...\n")

    totals: list[float] = []
    tails: list[float] = []

    for _ in range(arguments.runs):
        total, tail = measure_process(arguments.command)
        totals.append(total)
        tails.append(tail)

    phases, modules, heavy = measure_phases(arguments.command)

    print(f"{'Phase':<28} {'Median':>9} {'Min':>9}")
    print("-" * 48)
    print(f"{'import odev.common':<28} {phases[0]:>8.3f}s {'':>9}")
    print(f"{'init_framework + start':<28} {phases[1]:>8.3f}s {'':>9}")
    print(f"{'dispatch (command)':<28} {phases[2]:>8.3f}s {'':>9}")
    print(f"{'exit tail':<28} {statistics.median(tails):>8.3f}s {min(tails):>8.3f}s")
    print("-" * 48)
    print(f"{'total wall clock':<28} {statistics.median(totals):>8.3f}s {min(totals):>8.3f}s")

    print(f"\nImported modules: {modules}")
    print(f"Heavy modules loaded: {', '.join(heavy) if heavy else 'none'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
