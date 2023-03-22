from pathlib import Path

from odev.setup.completion import console, logger, setup
from tests.fixtures import Patch


class TestSetupSymlink:
    def test_setup_symlink(self):
        """Test the setup script responsible of creating a symlink to the bash completion script of odev.
        A symlink should be created on the file system.
        """
        with (
            Patch(logger, "warning"),
            Patch(console, "confirm", return_value=True),
        ):
            setup()

        assert Path("~/.local/share/bash-completion/completions/complete_odev.sh").expanduser().is_symlink()
