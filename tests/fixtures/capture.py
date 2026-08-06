import re
import sys
from io import StringIO

from odev.common.logging import logging


RE_STYLE_BLOCKS = r"\[[\w\s\.#]+\]([^\[]+)\[\/[\w\s\.#]+\]"


class CaptureOutput:
    """Context manager to capture stdout and stderr.

    Example:
        with CaptureOutput() as output:
            print("Hello, world!")
        assert output.stdout == "Hello, world!
    """

    def __init__(self):
        self._stdout = None
        self._stderr = None
        self._stdout_value = ""
        self._stderr_value = ""
        self._stdout_handler = None
        self._stderr_handler = None
        self._root_level = logging.NOTSET

    def __enter__(self):
        self._stdout = StringIO()
        self._stderr = StringIO()
        self._stdout_handler = logging.StreamHandler(self._stdout)
        self._stderr_handler = logging.StreamHandler(self._stderr)
        sys.stdout = self._stdout
        sys.stderr = self._stderr

        # Capture on the root logger rather than on each existing one: command modules are only imported when their
        # command runs, so their logger does not exist yet when the capture starts.
        root = logging.getLogger()
        self._root_level = root.level
        root.setLevel(logging.INFO)
        root.addHandler(self._stdout_handler)
        root.addHandler(self._stderr_handler)

        for logger in logging.Logger.manager.loggerDict.values():
            if isinstance(logger, logging.Logger):
                logger.propagate = True
                logger.setLevel(logging.INFO)

        return self

    def __exit__(self, *args):
        if self._stdout_handler is None or self._stderr_handler is None:
            raise AssertionError("CaptureOutput not properly initialized")

        root = logging.getLogger()
        root.removeHandler(self._stdout_handler)
        root.removeHandler(self._stderr_handler)
        root.setLevel(self._root_level)

        if self._stderr is None or self._stdout is None:
            raise AssertionError("CaptureOutput streams not properly initialized")

        self._stdout_value = re.sub(RE_STYLE_BLOCKS, r"\1", self._stdout.getvalue())
        self._stderr_value = re.sub(RE_STYLE_BLOCKS, r"\1", self._stderr.getvalue())
        self._stdout.close()
        self._stderr.close()
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__

    @property
    def stdout(self):
        if self._stdout and not self._stdout.closed:
            self._stdout_value = self._stdout.getvalue()

        self._stdout_value = re.sub(r"\x1b[^m]*m", "", self._stdout_value)
        return self._stdout_value

    @property
    def stderr(self):
        if self._stderr and not self._stderr.closed:
            self._stderr_value = self._stderr.getvalue()

        self._stderr_value = re.sub(r"\x1b[^m]*m", "", self._stderr_value)
        return self._stderr_value
