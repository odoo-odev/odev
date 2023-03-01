"""Common utilities for odev."""

# --- Import helper submodules -------------------------------------------------

from . import actions
from . import bash
from . import config
from . import logging
from . import odev
from . import odoo
from . import postgres
from . import progress
from . import prompt
from . import python
from . import signal_handling
from . import string
from . import style
from . import thread
from . import version

# --- Setup the framework and make it globally available -----------------------


global framework
framework = None


def init_framework():
    """Initialize the framework once."""
    global framework
    if framework is None:
        framework = odev.Odev()
    return framework
