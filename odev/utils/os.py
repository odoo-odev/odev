"""
Filesystem-specific utilities
"""

import os


def mkdir(path: str, perm: int = 0o777):
    """
    Creates a directory on the filesystem and sets its permissions.
    """

    os.makedirs(path, perm, exist_ok=True)
    os.chmod(path, perm)


def sizeof(num, suffix="B"):
    """
    Formats a number to its human readable representation in bytes-units.
    """
    for unit in ["", "K", "M", "G", "T", "P", "E", "Z"]:
        if abs(num) < 1024.0:
            return "{:3.1f} {unit}{suffix}".format(num, unit=unit, suffix=suffix)
        num /= 1024.0
    return "{:.1f} Y{suffix}".format(num, suffix=suffix)
