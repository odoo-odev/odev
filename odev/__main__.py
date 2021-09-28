#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os

# Explicitly initialize relative imports if run directly
if not __package__:
    package_dir = os.path.dirname(os.path.realpath(__file__))
    sys.path.append(os.path.normpath(os.path.join(package_dir, "..")))
    __package__ = os.path.basename(package_dir)

from signal import signal, SIGINT, SIGTERM
from subprocess import CalledProcessError

from odev.utils import logging
from odev.utils.github import self_update
from odev.structures.registry import CommandRegistry
from odev.exceptions.commands import CommandAborted, CommandMissing, InvalidArgument, InvalidQuery
from odev.exceptions.odoo import InvalidDatabase, InvalidOdooDatabase, RunningOdooDatabase

_logger = logging.getLogger(__name__)

code = 0


def signal_handler(signum, frame):
    global code
    print()  # Empty newline to make sure we're not writing next to a running prompt
    _logger.warning('Received signal (%s), exiting...' % (signum))
    code = signum
    exit(signum)


def main():
    '''
    Manages taking input from the user and calling the subsequent subcommands
    with the proper arguments as specified in the command line.
    '''
    global code

    signal(SIGINT, signal_handler)
    signal(SIGTERM, signal_handler)

    try:
        if self_update():
            # Restart the process with updated code
            os.execv(sys.argv.pop(0), sys.argv)

        registry = CommandRegistry().load_commands()
        code = registry.handle()
    except CommandAborted as e:
        _logger.info(e)
        code = 0
    except CalledProcessError as e:
        code = e.returncode
    except CommandMissing as e:
        _logger.error(str(e))
        code = 101
    except InvalidArgument as e:
        _logger.error(str(e))
        code = 102
    except InvalidDatabase as e:
        _logger.error(str(e))
        code = 201
    except InvalidOdooDatabase as e:
        _logger.error(str(e))
        code = 202
    except RunningOdooDatabase as e:
        _logger.error(str(e))
        code = 203
    except InvalidQuery as e:
        _logger.error(str(e))
        code = 204

    # ============================================================================== #
    # FIXME: implement custom exceptions to catch expected errors and graceful exit. #
    #        Keep raising on unexpected ones (that require code fix).                #
    # ============================================================================== #

    except Exception as e:
        _logger.error(str(e))
        code = 1
        raise
    finally:
        if code not in (None, 0):
            _logger.error(f'Exiting with code {code}')
