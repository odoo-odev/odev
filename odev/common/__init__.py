"""Common utilities for odev."""

from . import arguments as args
from . import odev

# --- Setup the framework and make it globally available -----------------------


global framework  # noqa: PLW0603, PLW0604
framework = None


def init_framework():
    """Initialize the framework once."""
    global framework  # noqa: PLW0603
    if framework is None:
        framework = odev.Odev()
    return framework
