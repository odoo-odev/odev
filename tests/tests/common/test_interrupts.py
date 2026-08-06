import os
from signal import SIGINT, getsignal

from odev.common.signal_handling import capture_signals

from tests.conftest import InterruptRecorder
from tests.fixtures import OdevTestCase


class TestSuiteInterrupts(OdevTestCase):
    """The suite has to stay stoppable while odev is holding the signal handlers.

    odev captures `SIGINT` around every query and every subprocess to cancel that operation rather than
    let the interrupt through. Without the recorder `conftest` installs, a `Ctrl+C` landing inside one of
    those blocks would be swallowed and the run would carry on.
    """

    def setUp(self):
        super().setUp()
        self.addCleanup(self.clear_interrupt)

    def clear_interrupt(self):
        """Forget the interrupt recorded by a test.

        Left set, the flag would stop the session before the next test rather than at the end of this one,
        taking the rest of the suite with it.
        """
        InterruptRecorder.interrupted = False

    def test_01_odev_handlers_are_wrapped(self):
        """The handlers odev installs should be the ones recording interrupts."""
        with capture_signals(handler=lambda *args: None):
            self.assertIsInstance(getsignal(SIGINT), InterruptRecorder)

    def test_02_interrupt_is_recorded_and_handled(self):
        """An interrupt captured by odev should reach its handler and be noted for the session."""
        handled: list[int] = []

        def handler(signal_number, *args):
            handled.append(signal_number)

        with capture_signals(handler=handler):
            os.kill(os.getpid(), SIGINT)

        self.assertEqual(handled, [SIGINT], "odev should still get a chance to cancel what it was doing")
        self.assertTrue(InterruptRecorder.interrupted, "the session should be stopped at the next test boundary")

    def test_03_handlers_are_wrapped_once(self):
        """Restoring a wrapped handler should not wrap it again, however many blocks are nested."""
        with capture_signals(handler=lambda *args: None):
            outer = getsignal(SIGINT)

            with capture_signals(handler=lambda *args: None):
                pass

            self.assertIs(getsignal(SIGINT), outer, "the outer handler should be restored as it was")
