'''Logging setup and customized logger code'''

import atexit
import io
import logging
from typing import Any, Dict, Union, Optional, Sequence, List
from getpass import getpass

from odev.utils.config import ConfigManager
from odev.constants import STYLE_RESET, SYMBOLS, THEMES, term


atexit.register(lambda: print(STYLE_RESET))

interactive: bool = True
assume_yes: bool = True


class LogRecord(logging.LogRecord):
    '''
    Custom implementation of LogRecord to add format specifiers
    '''

    symbol: str

    def __init__(self, name, level, pathname, lineno, msg, args, exc_info, func=None, sinfo=None, **kwargs):
        super().__init__(name, level, pathname, lineno, msg, args, exc_info, func=func, sinfo=sinfo, **kwargs)
        self.symbol = SYMBOLS.get(self.levelname, ' ')


class Logger(logging.getLoggerClass()):
    '''
    Custom implementation of logger, adding a few methods to transform it
    into an usable tool for interacting with the user
    '''

    def makeRecord(self, name, level, fn, lno, msg, args, exc_info, func=None, extra=None, sinfo=None):
        rv = LogRecord(name, level, fn, lno, msg, args, exc_info, func, sinfo)

        if extra is not None:
            for key in extra:
                if (key in ['message', 'asctime']) or (key in rv.__dict__):
                    raise KeyError('Attempt to overwrite %r in LogRecord' % key)
                rv.__dict__[key] = extra[key]
        return rv

    # Implemented later by `add_logging_level`,
    # included for IDE autocompletion/intellisense
    def success(self, *args, **kwargs):
        '''
        Logs a success message
        '''
        pass

    def format_question(
        self,
        question: str,
        choices: Optional[Union[str, Sequence[str]]] = None,
        default: Optional[str] = None,
        trailing: str = ' ',
        choices_sep: str = '/'
    ) -> str:
        text_parts: List[str] = [question]
        if isinstance(choices, (list, tuple)):
            choices = choices_sep.join(choices)
        if choices:
            text_parts.append(f'[{choices}]')
        if default:
            text_parts.append(f'({default})')

        _mem_logger_trap = io.StringIO()
        _mem_logger = getLogger(name='virtual', trap=_mem_logger_trap)
        _mem_logger.log(getattr(logging, 'QUESTION'), ' '.join(text_parts) + trailing)
        message = _mem_logger_trap.getvalue()
        _mem_logger_trap.close()
        return message.rstrip('\n')

    def confirm(self, question: str) -> bool:
        '''
        Asks the user to enter Y or N (case-insensitive).
        '''
        if not interactive:
            return assume_yes

        choices = ['y', 'n']
        answer: str = ''
        message = self.format_question(question, choices=choices)
        while answer not in choices:
            answer = input(message)[0].lower()
        return answer == 'y'

    def ask(self, question: str, default: Optional[str] = None) -> str:
        '''
        Asks something to the user.
        '''
        message = self.format_question(question, default=default)
        answer: str = input(message)
        if default and not answer:
            return default
        return answer

    def password(self, question: str):
        '''
        Asks for a password.
        '''
        message = self.format_question(question)
        return getpass(message)


logging.setLoggerClass(Logger)
LoggerType = Union[logging.LoggerAdapter, Logger]


def add_logging_level(name: str, value: int, method_name: Optional[str] = None):
    if method_name is None:
        method_name = name.lower()

    def log_for_level_method(self, msg, *args, **kwargs):
        nonlocal value
        if self.isEnabledFor(value):
            self._log(value, msg, args, **kwargs)

    setattr(logging, name, value)
    logging.addLevelName(value, name)
    setattr(logging.getLoggerClass(), method_name, log_for_level_method)


add_logging_level('SUCCESS', 25)
add_logging_level('QUESTION', 100)


class ColorFormatter(logging.Formatter):
    '''
    Custom log formatter class to colorize log levels in console output
    '''

    config: Dict[str, str]
    theme: Dict[str, Any]

    def __init__(self, fmt: Optional[str] = None, *args, **kwargs):
        self.config = ConfigManager('odev').load().get('logger', {})
        self.theme = THEMES.get(self.config.get('theme', 'minimal'), THEMES['minimal'])

        fmt = fmt or self.theme.get('format', self.theme.get('format'))
        kwargs.setdefault('datefmt', self.theme.get('dateformat'))

        super().__init__(fmt, *args, **kwargs)

    def format(self, record: logging.LogRecord) -> str:
        if record.levelname in self.theme['colors']:
            record.__dict__['log_color'] = self.theme['colors'][record.levelname]
        return super().format(record)


def getLogger(name: Optional[str] = None, trap: Optional[io.StringIO] = None) -> Logger:
    '''
    Creates a supercharged logger instance
    '''
    logger = logging.getLogger(name)
    logger.propagate = False

    if not logger.hasHandlers() or trap is not None:
        for handler in logger.handlers:
            logger.removeHandler(handler)

        log_handler = logging.StreamHandler(trap)
        log_handler.setFormatter(ColorFormatter())
        logger.addHandler(log_handler)
        logger.setLevel(logging.INFO)

    return logger


_root_logger = getLogger()


def set_log_level(level: str) -> None:
    '''
    Set the log level for the base logger
    :param level: the level to set for the logger as a string
    '''
    global _root_logger
    _root_logger.setLevel(level)
