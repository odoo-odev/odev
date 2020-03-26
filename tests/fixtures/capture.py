import sys
from io import StringIO
import re


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

    def __enter__(self):
        self._stdout = StringIO()
        self._stderr = StringIO()
        sys.stdout = self._stdout
        sys.stderr = self._stderr
        return self

    def __exit__(self, *args):
        self._stdout_value = self._stdout.getvalue()
        self._stderr_value = self._stderr.getvalue()
        self._stdout.close()
        self._stderr.close()
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__

    @property
    def stdout(self):
        if not self._stdout.closed:
            self._stdout_value = self._stdout.getvalue()

        self._stdout_value = re.sub(r"\x1b[^m]*m", "", self._stdout_value)
        return self._stdout_value

    @property
    def stderr(self):
        if not self._stderr.closed:
            self._stderr_value = self._stderr.getvalue()

        self._stderr_value = re.sub(r"\x1b[^m]*m", "", self._stdout_value)
        return self._stderr_value
