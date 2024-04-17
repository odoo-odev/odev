from signal import SIGINT

from odev.common.signal_handling import signal_handler_exit
from tests.fixtures import OdevTestCase


class TestCommonSignalHandling(OdevTestCase):
    """Test the signal handling functions."""

    def test_01_exit(self):
        """Signal handler should exit."""
        with self.assertRaises(SystemExit):
            signal_handler_exit(SIGINT)
