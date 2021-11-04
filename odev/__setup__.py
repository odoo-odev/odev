#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import stat
from pathlib import Path
from typing import List, Tuple
from signal import signal, SIGINT, SIGTERM

from odev.utils import logging
from odev.utils.os import mkdir
from odev.utils.config import ConfigManager


_logger = logging.getLogger(__name__)


def signal_handler(signum, frame):
    print()  # Empty newline to make sure we're not writing next to a running prompt
    _logger.warning('Received signal (%s), aborting setup...' % (signum))
    exit(signum)


def run():
    '''
    Setup wizard for odev
    '''

    signal(SIGINT, signal_handler)
    signal(SIGTERM, signal_handler)

    _logger.warning(
        'This script is about to write to different files accross your '
        'system and might need root permissions if you try to write to files '
        'that are out of your user scope ' + logging.term.bold_underline('(not recommended)')
    )

    # User input is needed for locations in which data is stored
    # We use a list of tuples to create missing directories
    # based on the answer to questions asked to the user
    # Tuple format: ('key_in_config', 'Question string?', 'default value')
    ASK_DIRS: List[Tuple[str, str, str]] = [
        ('odoo', 'Where do you want to store Odoo\'s repositories on your machine?', '~/odoo/versions'),
        ('dump', 'Where do you want to store Odoo databases\' dump files?', '~/odoo/dumps'),
        ('dev', 'Where do you want to store your Odoo custom developments repositories?', '~/odoo/dev'),
    ]

    try:
        ubin = os.path.join('/usr', 'local', 'bin', 'odev')

        if os.path.exists(ubin) or os.path.islink(ubin):
            os.remove(ubin)

        cwd = os.getcwd()
        main = os.path.join(cwd, 'main.py')
        os.symlink(main, ubin)
        os.chmod(main, os.stat(main).st_mode | stat.S_IEXEC)

        ConfigManager('databases')
        odev_config = ConfigManager('odev')

        odev_config.config['paths'] = odev_config.config.get('paths', {})
        odev_config.config['paths']['odev'] = cwd

        for key, question, default in ASK_DIRS:
            answer = _logger.ask(question, odev_config.config['paths'].get(key, default))
            path = os.path.expanduser(answer)
            odev_config.config['paths'][key] = path
            mkdir(path)

        odev_config.save()

    except Exception as exception:
        _logger.error(exception)
        exit(1)
