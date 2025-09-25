import sys


if sys.version_info < (3, 10):  # noqa: UP036
    raise RuntimeError("Odev requires Python 3.10 or later")
