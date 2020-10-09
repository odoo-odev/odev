# -*- coding: utf-8 -*-

import re
import os
from getpass import getpass
from clint.textui import puts, colored

quotes = {
    'info': colored.blue('[i]', False, True),
    'success': colored.green('[*]', False, True),
    'warning': colored.yellow('[!]', False, True),
    'error': colored.red('[-]', False, True),
    'debug': colored.black('[#]', False, True),
    'question': colored.magenta('[?]', False, True),
}

re_blanks = re.compile(r'([-\s]+)')
re_extras = re.compile(r'([^a-z0-9-_\s])')
re_psql = re.compile(r'^(pg_|[0-9])')


def sanitize(name: str):
    """
    Sanitizes the name of a database so that it can be used without creating
    any conflict in PostgreSQL due to improper formatting or forbidden
    characters.
    """

    require('name', name)

    name = str(name).lower()
    name = re_extras.sub('', name)
    name = re_blanks.sub('_', name)

    if re_psql.search(name):
        raise ValueError(name)

    return name


def require(name: str, value: str):
    """
    Makes sure a value is set, otherwise raise an exception.
    """

    if not value:
        raise Exception("Value \'%s\' is required; none given" % (name))


def log(level: str, text: str):
    """
    Prints a log message to the console.
    """

    puts('%s %s' % (quotes[level], text))


def confirm(question: str):
    """
    Asks the user to enter Y or N (case-insensitive).
    """
    answer = ''

    while answer not in ['y', 'n']:
        answer = input('%s %s [y/n] ' % (quotes['question'], question))[0].lower()
    
    return answer == 'y'


def ask(question: str, default=False):
    """
    Asks something to the user.
    """

    if default:
        return input('%s %s [%s] ' % (quotes['question'], question, default)) or default
    return input('%s %s ' % (quotes['question'], question))


def password(question: str):
    """
    Asks for a password.
    """

    return getpass(prompt='%s %s ' % (quotes['question'], question))


def mkdir(path: str, perm: int = 0o777):
    """
    Creates a directory on the filesystem and sets its permissions.
    """

    os.makedirs(path, perm, exist_ok=True)
    os.chmod(path, perm)
