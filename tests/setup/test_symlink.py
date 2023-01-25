from pathlib import Path

from odev.setup.symlink import logger, prompt, setup
from tests.fixtures import Patch


class TestSetupSymlink:
    def test_setup_symlink(self):
        """Test the setup script responsible of creating a symlink to odev.
        A symlink should be created to map the "odev" command to the main file of this application.
        """
        with (
            Patch(logger, "warning"),
            Patch(prompt, "confirm", return_value=True),
        ):
            setup()

        assert Path("~/.local/bin/odev").expanduser().is_symlink()
