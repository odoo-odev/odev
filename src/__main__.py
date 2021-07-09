# -*- coding: utf-8 -*-

from signal import signal, SIGINT, SIGTERM
from subprocess import CalledProcessError

from . import utils, cli


code = 0


def signal_handler(signum, frame):
    global code
    utils.log('warning', 'Received signal (%s), exiting...' % (signum))
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
        utils.log('error', str(exception))
        code = 1
    finally:
        level = 'success'

        if code > 0:
            level = 'error'

    if level != 'success':
        utils.log(level, 'Exiting with code %s' % (code))


if __name__ == "__main__":
    main()
