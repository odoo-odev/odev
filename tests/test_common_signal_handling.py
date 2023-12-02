from signal import SIGINT

import pytest

from odev.common.signal_handling import signal_handler_exit
from tests.fixtures import OdevTestCase


class TestCommonSignalHandling(OdevTestCase):
    def test_signal_handler_exit(self):
        """Signal handler should exit."""
        with pytest.raises(SystemExit):
            signal_handler_exit(SIGINT)
