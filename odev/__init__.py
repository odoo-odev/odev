import sys


if sys.version_info < (3, 10, 12):
    current_version = ".".join(map(str, sys.version_info[:3]))
    raise RuntimeError(f"Odev requires Python 3.10.12 or later, current version: {current_version}")
