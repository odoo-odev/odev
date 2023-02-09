"""Styling and theming variables."""

from rich.console import Console
from rich.highlighter import ReprHighlighter, _combine_regex
from rich.theme import Theme


BLACK = "#8a909c"
CYAN = "#00afaf"
GRAY = ""  # Default text color from terminal settings
GREEN = "#98C379"
PURPLE = "#af5faf"
RED = "#ec6047"
YELLOW = "#d19a66"

# --- Theme --------------------------------------------------------------------

RICH_THEME = Theme(
    {
        "bar.back": "black",
        "bar.complete": PURPLE,
        "bar.finished": PURPLE,
        "bar.pulse": PURPLE,
        "logging.level.critical": f"bold {RED}",
        "logging.level.debug": f"bold {GRAY}",
        "logging.level.error": f"bold {RED}",
        "logging.level.info": f"bold {CYAN}",
        "logging.level.warning": f"bold {YELLOW}",
        "progress.data.speed": CYAN,
        "progress.description": GRAY,
        "progress.download": CYAN,
        "progress.elapsed": BLACK,
        "progress.filesize.total": f"bold {CYAN}",
        "progress.filesize": CYAN,
        "progress.percentage": f"bold {PURPLE}",
        "progress.remaining": CYAN,
        "progress.spinner": PURPLE,
        "repr.boolean_false": f"italic {RED}",
        "repr.boolean_true": f"italic {GREEN}",
        "repr.call": CYAN,
        "repr.filename": PURPLE,
        "repr.none": f"italic {CYAN}",
        "repr.number_complex": CYAN,
        "repr.number": CYAN,
        "repr.odev": f"bold {CYAN}",
        "repr.path": PURPLE,
        "repr.str": CYAN,
        "repr.url": PURPLE,
        "repr.version": f"bold {CYAN}",
        "repr.package_name": f"bold {PURPLE}",
        "repr.package_op": GRAY,
        "repr.package_version": f"bold {CYAN}",
        "status.spinner": f"bold {PURPLE}",
    }
)


# --- Logging highlighter customization ----------------------------------------
# This is not useful at all, but it's fun to have. I guess...


class OdevReprHighlighter(ReprHighlighter):
    """Extension of `ReprHighlighter` to highlight odev version numbers."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.highlights[-1] = _combine_regex(
            r"(?P<odev>odev)",
            r"(?P<version>([0-9]+\.){2,}[0-9]+)",
            r"(?:(?P<package_name>[\w_-]+)(?:(?P<package_op>[<>=]+)(?P<package_version>[\d.]+)))",
            self.highlights[-1],
        )


# --- Bare rich console --------------------------------------------------------

console = Console(highlighter=None, theme=RICH_THEME)
repr_console = Console(highlighter=OdevReprHighlighter(), theme=RICH_THEME)


# --- Spinner context manager --------------------------------------------------


def spinner(message: str):
    """Context manager to display a spinner while executing code.

    :param message: The message to display.
    :type message: str
    """
    status = repr_console.status(repr_console.render_str(message), spinner="arc")
    status._spinner.frames = [f"[{frame}]" for frame in status._spinner.frames]
    return status
