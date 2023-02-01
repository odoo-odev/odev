"""Styling and theming variables."""

from rich.console import Console
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
        "status.spinner": GRAY,
    }
)

# --- Bare rich console --------------------------------------------------------

console = Console(highlighter=None, theme=RICH_THEME)
