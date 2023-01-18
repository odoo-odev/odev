"""Styling and theming variables."""

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
        "logging.level.debug": f"bold {GRAY}",
        "logging.level.info": f"bold {CYAN}",
        "logging.level.warning": f"bold {YELLOW}",
        "logging.level.error": f"bold {RED}",
        "logging.level.critical": f"bold {RED}",
        "repr.boolean_false": f"italic {RED}",
        "repr.boolean_true": f"italic {GREEN}",
        "repr.call": CYAN,
        "repr.filename": PURPLE,
        "repr.none": f"italic {CYAN}",
        "repr.number": CYAN,
        "repr.number_complex": CYAN,
        "repr.odev": f"bold {CYAN}",
        "repr.path": PURPLE,
        "repr.str": CYAN,
        "repr.url": PURPLE,
        "repr.version": f"bold {CYAN}",
    }
)
