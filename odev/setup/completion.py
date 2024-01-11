"""Setup auto completion script for odev commands and databases.

See:
- https://github.com/scop/bash-completion/
- https://www.gnu.org/savannah-checkouts/gnu/bash/manual/html_node/Programmable-Completion.html
"""

from pathlib import Path

from odev.common.config import Config
from odev.common.console import console
from odev.common.logging import logging


logger = logging.getLogger(__name__)


# --- Values -------------------------------------------------------------------


file_path = Path(__file__).parents[2] / "complete_odev.sh"
comp_path = Path("~/.local/share/bash-completion/completions/complete_odev.sh").expanduser()


# --- Setup --------------------------------------------------------------------


def setup(config: Config) -> None:
    """Setup auto completion script for odev commands and databases.

    See:
    - https://github.com/scop/bash-completion/
    - https://www.gnu.org/savannah-checkouts/gnu/bash/manual/html_node/Programmable-Completion.html

    :param config: Odev configuration
    """

    if not comp_path.parent.exists():
        logger.debug(f"Directory {comp_path.parent} does not exist, creating it")
        comp_path.parent.mkdir(parents=True)

    if comp_path.exists():
        logger.warning(f"Symlink path {comp_path} already exists, this is used to enable bash auto-completion")

        if console.confirm("Would you like to overwrite it?"):
            logger.debug(f"Removing symlink path {comp_path}")
            comp_path.unlink(missing_ok=True)

    if not comp_path.exists():
        logger.debug(f"Creating symlink from {comp_path} to {file_path}")
        comp_path.symlink_to(file_path)
