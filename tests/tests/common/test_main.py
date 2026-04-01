from bdb import BdbQuit
from signal import SIGINT, SIGTERM
from unittest.mock import MagicMock

from odev import __main__ as main_module
from odev.common.errors.odev import OdevError

from tests.fixtures import OdevTestCase


class TestMainEntrypoint(OdevTestCase):
    def test_01_main_success(self):
        with (
            self.patch("odev.__main__.os", "geteuid", return_value=1000),
            self.patch("odev.__main__", "signal") as mock_signal,
            self.patch("odev.common", "init_framework", return_value=self.odev) as mock_init_framework,
            self.patch(self.odev, "dispatch", return_value=True),
            self.assertRaises(SystemExit) as exited,
        ):
            main_module.main()

        self.assertEqual(exited.exception.code, 0)
        self.assertEqual(mock_signal.call_count, 2)
        registered_signals = {call.args[0] for call in mock_signal.call_args_list}
        self.assertEqual(registered_signals, {SIGINT, SIGTERM})
        mock_init_framework.assert_called_once_with()

    def test_02_main_as_root_exits(self):
        with (
            self.patch("odev.__main__.os", "geteuid", return_value=0),
            self.patch("odev.__main__.sys", "exit", side_effect=SystemExit(1)),
            self.assertRaises(SystemExit),
        ):
            main_module.main()

    def test_03_main_keyboard_interrupt(self):
        with (
            self.patch("odev.__main__.os", "geteuid", return_value=1000),
            self.patch("odev.common", "init_framework", side_effect=KeyboardInterrupt),
            self.patch("odev.common.signal_handling", "signal_handler_exit") as mock_signal_handler_exit,
        ):
            main_module.main()

        mock_signal_handler_exit.assert_called_once_with(SIGINT, None)

    def test_04_main_bdb_quit_exits(self):
        with (
            self.patch("odev.__main__.os", "geteuid", return_value=1000),
            self.patch("odev.common", "init_framework", side_effect=BdbQuit),
            self.patch("odev.__main__.sys", "exit", side_effect=SystemExit(1)),
            self.assertRaises(SystemExit),
        ):
            main_module.main()

    def test_05_main_odev_error_exits(self):
        mock_logger = MagicMock()
        with (
            self.patch("odev.__main__.os", "geteuid", return_value=1000),
            self.patch("odev.common", "init_framework", side_effect=OdevError("expected failure")),
            self.patch("odev.common.logging.logging", "getLogger", return_value=mock_logger),
            self.patch("odev.__main__.sys", "exit", side_effect=SystemExit(1)),
            self.assertRaises(SystemExit),
        ):
            main_module.main()

        mock_logger.error.assert_called_once()
        self.assertIsInstance(mock_logger.error.call_args[0][0], OdevError)

    def test_06_main_unhandled_exception_exits(self):
        mock_logger = MagicMock()
        with (
            self.patch("odev.__main__.os", "geteuid", return_value=1000),
            self.patch("odev.common", "init_framework", side_effect=RuntimeError("unexpected")),
            self.patch("odev.common.logging.logging", "getLogger", return_value=mock_logger),
            self.patch("odev.__main__.sys", "exit", side_effect=SystemExit(1)),
            self.assertRaises(SystemExit),
        ):
            main_module.main()

        mock_logger.error.assert_called_once()
        err_arg = mock_logger.error.call_args[0][0]
        self.assertIn("Execution failed", err_arg)
        self.assertIn("RuntimeError", err_arg)
        tb_logged = any(call.args and "Traceback" in str(call.args[0]) for call in mock_logger.debug.call_args_list)
        self.assertTrue(tb_logged)
