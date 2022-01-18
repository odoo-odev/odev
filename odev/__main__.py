#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import re

# Explicitly initialize relative imports if run directly
if not __package__:
    package_dir = os.path.dirname(os.path.realpath(__file__))
    sys.path.append(os.path.normpath(os.path.join(package_dir, '..')))
    __package__ = os.path.basename(package_dir)

from signal import signal, SIGINT, SIGTERM
from subprocess import CalledProcessError
from git.exc import GitCommandError

from odev.utils import logging
from odev.utils.github import self_update, handle_git_error
from odev.structures.registry import CommandRegistry
from odev.exceptions.commands import CommandAborted, CommandMissing, InvalidArgument, InvalidQuery
from odev.exceptions.odoo import InvalidDatabase, InvalidOdooDatabase, RunningOdooDatabase
from odev.exceptions.odoo_sh import SHConnectionError, SHDatabaseTooLarge

_logger = logging.getLogger(__name__)

code = 0

def signal_handler(signum, frame):
    global code
    print()  # Empty newline to make sure we're not writing next to a running prompt
    _logger.warning('Received signal (%s), exiting...' % (signum))
    code = signum
    exit(signum)


def set_log_level():
    # Set global log level before registering commands to support custom
    # log-levels everywhere
    re_loglevel = re.compile(r'(?:-v\s?|--log-level(?:\s|=){1})([a-z]+)', re.IGNORECASE)
    loglevel_match = re_loglevel.findall(' '.join(sys.argv))

    # TODO: Default fall back to set INFO log level before arg parse.
    level = 'INFO'
    if loglevel_match and loglevel_match[~0] in logging.logging._nameToLevel:
        level = loglevel_match[~0]

    logging.set_log_level(level)


def main():
    '''
    Manages taking input from the user and calling the subsequent subcommands
    with the proper arguments as specified in the command line.
    '''
    global code

    signal(SIGINT, signal_handler)
    signal(SIGTERM, signal_handler)

    try:
        set_log_level()

        if self_update():
            # Restart the process with updated code
            os.execv(sys.argv[0], sys.argv)

        registry = CommandRegistry()
        registry.run_upgrades()
        registry.load_commands()
        code = registry.handle()

    # Process

    except CommandAborted as e:
        _logger.info(e)
        code = 0
    except CalledProcessError as e:
        code = e.returncode

    # Git

    except GitCommandError as e:
        code = handle_git_error(e)

    # Commands registry

    except CommandMissing as e:
        _logger.error(str(e))
        code = 101
    except InvalidArgument as e:
        _logger.error(str(e))
        code = 102

    # Commands

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

    # Odoo SH

    except SHConnectionError as e:
        _logger.error(str(e))
        code = 301
    except SHDatabaseTooLarge as e:
        _logger.error(str(e))
        code = 302

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
