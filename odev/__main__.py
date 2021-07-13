#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Explicitly initialize relative imports if run directly
if not __package__:
    import sys
    import os
    package_dir = os.path.dirname(os.path.realpath(__file__))
    sys.path.append(os.path.normpath(os.path.join(package_dir, "..")))
    __package__ = os.path.basename(package_dir)

import logging
from signal import signal, SIGINT, SIGTERM
from subprocess import CalledProcessError

from . import cli


_logger = logging.getLogger(__name__)


code = 0


def signal_handler(signum, frame):
    global code
    _logger.warning('Received signal (%s), exiting...' % (signum))
    code = signum


def main():
    """
    Manages taking input from the user and calling the subsequent subcommands
    with the proper arguments as specified in the command line.
    """
    global code

    signal(SIGINT, signal_handler)
    signal(SIGTERM, signal_handler)

    try:
        code = cli.main()
    except CalledProcessError as proc_exception:
        code = proc_exception.returncode
    except Exception as exception:
        raise  # FIXME: for testing
        _logger.error(str(exception))
        code = 1
        # FIXME: implement custom exceptions to catch expected errors and graceful exit.
        #        Keep raising on unexpected ones (that require code fix).
        raise
    finally:
        level = "SUCCESS"

        if code > 0:
            level = "ERROR"

    if code != 0:
        _logger.log(logging.getLevelName(level), f"Exiting with code {code}")


if __name__ == "__main__":
    main()
