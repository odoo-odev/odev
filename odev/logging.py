"""Logging setup and customized logger code"""

import logging
from typing import MutableMapping, Union, Optional, Any

import atexit

from blessed import Terminal


__all__ = ["term", "set_log_level", "LoggerType"]


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


LoggerType = Union[logging.Logger, logging.LoggerAdapter]

term = Terminal()
STYLE_RESET: str = term.normal
atexit.register(lambda: print(STYLE_RESET))

add_logging_level("SUCCESS", 25)


class ColorFormatter(logging.Formatter):
    """
    Custom log formatter class to colorize log levels in console output
    """

    LOG_DATEFORMAT: str = "%Y-%m-%d %H:%M:%S"
    LOG_FORMAT: str = (
        f"%(log_color)s[%(levelname)s]{STYLE_RESET} "
        f"{term.maroon4}%(asctime)s{STYLE_RESET} "
        f"{term.maroon1}%(name)s{STYLE_RESET}: %(message)s"
    )
    LOG_COLORS: MutableMapping[str, int] = {
        "NOTSET": term.darkgray,
        "DEBUG": term.steelblue4,
        "INFO": term.bright_blue,
        "SUCCESS": term.bright_green,
        "WARNING": term.bright_yellow,
        "ERROR": term.bright_red,
        "CRITICAL": term.darkred,
    }

    def __init__(self, fmt: Optional[str] = None, *args, **kwargs):
        if fmt is None:
            fmt = self.LOG_FORMAT
        kwargs.setdefault("datefmt", self.LOG_DATEFORMAT)
        super().__init__(fmt, *args, **kwargs)

    def format(self, record: logging.LogRecord) -> str:
        if record.levelname in self.LOG_COLORS:
            record.__dict__["log_color"] = self.LOG_COLORS[record.levelname]
        return super().format(record)


# Setup the log for the project
_root_logger: logging.Logger = logging.getLogger()
log_handler: logging.StreamHandler = logging.StreamHandler()
log_handler.setFormatter(ColorFormatter())
_root_logger.addHandler(log_handler)
_root_logger.setLevel(logging.INFO)


def set_log_level(level: str) -> None:
    """
    Set the log level for the base logger
    :param level: the level to set for the logger as a string
    """
    global _root_logger
    _root_logger.setLevel(level)
