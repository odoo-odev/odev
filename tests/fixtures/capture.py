import re
import sys
from io import StringIO

from odev.common.console import RICH_THEME
from odev.common.logging import logging


RE_STYLE_BLOCKS = rf"\[\/?({'|'.join([re.escape(style) for style in RICH_THEME.styles.keys()])})\]"


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

    def __enter__(self):
        self._stdout = StringIO()
        self._stderr = StringIO()
        self._stdout_handler = logging.StreamHandler(self._stdout)
        self._stderr_handler = logging.StreamHandler(self._stderr)
        sys.stdout = self._stdout
        sys.stderr = self._stderr

        for logger in logging.Logger.manager.loggerDict.values():
            if isinstance(logger, logging.Logger):
                logger.propagate = True
                logger.setLevel(logging.INFO)
                logger.addHandler(self._stdout_handler)
                logger.addHandler(self._stderr_handler)

        return self

    def __exit__(self, *args):
        assert self._stdout_handler is not None
        assert self._stderr_handler is not None

        for logger in logging.Logger.manager.loggerDict.values():
            if isinstance(logger, logging.Logger):
                logger.removeHandler(self._stdout_handler)
                logger.removeHandler(self._stderr_handler)

        assert self._stderr is not None
        assert self._stdout is not None

        self._stdout_value = re.sub(RE_STYLE_BLOCKS, "", self._stdout.getvalue())
        self._stderr_value = re.sub(RE_STYLE_BLOCKS, "", self._stderr.getvalue())
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

        self._stderr_value = re.sub(r"\x1b[^m]*m", "", self._stdout_value)
        return self._stderr_value
