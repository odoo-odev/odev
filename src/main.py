# -*- coding: utf-8 -*-

# - Clint (args + columns)
from clint import arguments
from signal import signal, SIGINT, SIGTERM
from subprocess import CalledProcessError

from . import utils
from .scripts.dispatcher import dispatcher


def signal_handler(signum, frame):
    utils.log('warning', 'Received signal (%s), exiting...' % (signum))
    code = signum


def cli():
    """
    Manages taking input from the user and calling the subsequent subcommands
    with the proper arguments as specified in the command line.
    """

    global code
    code = 0

    signal(SIGINT, signal_handler)
    signal(SIGTERM, signal_handler)

    try:
        args = arguments.Args()
        command, database, args = parse_args(args)
        code = dispatch(command, database, args)
    except CalledProcessError as proc_exception:
        code = proc_exception.returncode
    except Exception as exception:
        utils.log('error', exception)
        code = 1
    finally:
        level = 'success'

        if code > 0:
            level = 'error'

        utils.log(level, 'Exiting with code %s' % (code))


def dispatch(command, database, options):
    """
    Runs the selected subcommand on the selected database.
    """

    if database:
        database = utils.sanitize(database)
    else:
        database = ''

    result = dispatcher[command].run(database, options)

    if result != 0:
        raise Exception('An error occured during the execution of command \'%s\'' % (command))

    return result


def parse_args(args):
    """
    Parses arguments given by the user in the command line interface.
    """

    if not args[0]:
        raise Exception('odev requires at least one argument; none given')

    command = args.pop(0)

    if args[0]:
        database = args.pop(0)
    else:
        database = None

    return command, database, args
