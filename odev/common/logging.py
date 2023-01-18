"""Logging configuration for odev.

To be used with:
```py
from odev.common import logging

logger = logging.getLogger(__name__)
```
"""

# TODO: Implement tree line (command-defined color)

import logging
import re
import sys
from logging import LogRecord
from typing import Dict, Literal, Union

from rich.console import Console
from rich.highlighter import ReprHighlighter, _combine_regex
from rich.logging import RichHandler
from rich.text import Text
from rich.theme import Theme

from odev.common import style


__all__ = ["logging", "console", "LOG_LEVEL"]


# --- Logging configuration ----------------------------------------------------
# Infer log level from command line arguments or default to INFO

__log_level = re.search(
    r"\s(?:-v\s?|--log-level(?:\s|=){1})([a-z]+)",
    " ".join(sys.argv),
    re.IGNORECASE,
)

LOG_LEVEL = __log_level.group(1).upper() if __log_level else "INFO"

SILENCED_LOGGERS = ["git.cmd", "asyncio", "urllib3", "rich", "pip._internal"]


# --- Logging handler customization --------------------------------------------
# Display the log level as a single character


class OdevRichHandler(RichHandler):
    """Custom `RichHandler` to show the log level as a single character.
    See `rich.logging.RichHandler`.
    """

    symbols: Dict[Union[int, Literal["default"]], str] = {
        logging.CRITICAL: "~",
        logging.ERROR: "-",
        logging.WARNING: "!",
        logging.INFO: "i",
        logging.DEBUG: "#",
        "default": "?",
    }

    def get_level_text(self, record: LogRecord) -> Text:
        """Get the level name from the record.

        :param LogRecord record: LogRecord instance.
        :return: A tuple of the style and level name.
        :rtype: Text
        """

        symbol = self.symbols.get(record.levelno, self.symbols["default"])
        level_text = super().get_level_text(record)
        level_text.plain = f"[{symbol}]".ljust(3)
        return level_text


# --- Logging highlighter customization ----------------------------------------
# This is not useful at all, but it's fun to have. I guess...


class OdevReprHighlighter(ReprHighlighter):
    """Extension of `ReprHighlighter` to highlight odev version numbers."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.highlights[-1] = _combine_regex(
            r"(?P<odev>odev)",
            r"(?P<version>([0-9]+\.){2,}[0-9]+)",
            self.highlights[-1],
        )


# --- Logging console initialization -------------------------------------------
# Initialize a rich console with a custom theme

console = Console(
    highlighter=OdevReprHighlighter(),
    theme=Theme(
        {
            "logging.level.debug": f"bold {style.GRAY}",
            "logging.level.info": f"bold {style.CYAN}",
            "logging.level.warning": f"bold {style.YELLOW}",
            "logging.level.error": f"bold {style.RED}",
            "logging.level.critical": f"bold {style.RED}",
            "repr.boolean_false": f"italic {style.RED}",
            "repr.boolean_true": f"italic {style.GREEN}",
            "repr.call": style.CYAN,
            "repr.filename": style.PURPLE,
            "repr.none": f"italic {style.CYAN}",
            "repr.number": style.CYAN,
            "repr.number_complex": style.CYAN,
            "repr.odev": f"bold {style.CYAN}",
            "repr.path": style.PURPLE,
            "repr.str": style.CYAN,
            "repr.url": style.PURPLE,
            "repr.version": f"bold {style.CYAN}",
        }
    ),
)


# --- Logging module initialization --------------------------------------------
# Initialize the logging module with a rich handler, formatter and set its level

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(message)s",
    handlers=[
        OdevRichHandler(
            rich_tracebacks=True,
            tracebacks_show_locals=True,
            show_time=False,
            console=console,
            markup=True,
        )
    ],
)

for logger in SILENCED_LOGGERS:
    logging.getLogger(logger).setLevel(logging.WARNING)