"""Setup auto completion script for odev commands and databases.

See:
- https://github.com/scop/bash-completion/
- https://www.gnu.org/savannah-checkouts/gnu/bash/manual/html_node/Programmable-Completion.html
"""

from pathlib import Path
from typing import Optional

from odev.common import prompt
from odev.common.config import ConfigManager
from odev.common.logging import logging


logger = logging.getLogger(__name__)


# --- Setup --------------------------------------------------------------------


def setup(config: Optional[ConfigManager] = None) -> None:
    """Setup auto completion script for odev commands and databases.

    See:
    - https://github.com/scop/bash-completion/
    - https://www.gnu.org/savannah-checkouts/gnu/bash/manual/html_node/Programmable-Completion.html

    :param config: Configuration manager
    """

    file_path = Path(__file__).parents[2] / "complete_odev.sh"
    comp_path = Path("~/.local/share/bash-completion/completions/complete_odev.sh").expanduser()

    if not comp_path.parent.exists():
        logger.debug(f"Directory {comp_path.parent} does not exist, creating it")
        comp_path.parent.mkdir(parents=True)

    if comp_path.exists():
        logger.warning(f"Symlink path {comp_path} already exists")

        if prompt.confirm("Would you like to overwrite it?"):
            logger.debug(f"Removing symlink path {comp_path}")
            comp_path.unlink(missing_ok=True)

    if not comp_path.exists():
        logger.debug(f"Creating symlink from {comp_path} to {file_path}")
        comp_path.symlink_to(file_path)
