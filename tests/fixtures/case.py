import shlex
from typing import ClassVar, List
from unittest import TestCase
from unittest.mock import PropertyMock, _patch, patch

from testfixtures import Replacer
from testfixtures.popen import MockPopen

from odev.common.commands.base import Command
from odev.common.connectors import Connector
from odev.common.databases import Database
from odev.common.odev import Odev
from odev.common.odoobin import OdoobinProcess


odev = Odev(test=True)


class OdevTestCase(TestCase):
    """Base test class for Odev structures and commands."""

    odev: ClassVar[Odev] = odev
    """The Odev instance to use for testing."""

    __patches: ClassVar[List[_patch]] = []
    """The patches applied to the test case."""

    def setUp(self):
        if not self.odev.in_test_mode:
            self.fail("Odev is not in test mode, failing test to prevent accidental damage")

    @classmethod
    def setUpClass(cls):
        for patched_cls in (Connector, Database, OdoobinProcess):
            patched = cls.patch_property(patched_cls, "odev", return_value=cls.odev)
            cls.__patches.append(patched)
            patched.start()
        cls.addClassCleanup(cls.tearDownClass)
        cls.odev.start()

    @classmethod
    def tearDownClass(cls):
        for patched in cls.__patches:
            patched.stop()

    @classmethod
    def patch(cls, obj, attr, **kwargs):
        """Patch an object's attribute."""
        return patch.object(obj, attr, **kwargs)

    @classmethod
    def patch_property(cls, obj, attr, **kwargs):
        """Patch an object's property."""
        return patch.object(obj, attr, new_callable=PropertyMock, **kwargs)

    def setup_command(self, command: str, arguments: str = "", keep_quotes: bool = True) -> Command:
        """Setup a command for testing.
        :param command: The name of the command to setup.
        :param arguments: The arguments to pass to the command.
        :param keep_quotes: Whether to keep quotes in the arguments when spliting them.
        """
        command_cls = self.odev.commands[command]
        namespace = self.odev.parse_arguments(command_cls, *shlex.split(arguments, posix=not keep_quotes))
        return command_cls(namespace)  # type: ignore[misc] # CommandType? is not callable


class OdevCommandTestCase(OdevTestCase):
    """Base test class for testing Odev commands."""

    @classmethod
    def setUpClass(cls):
        # Mock Popen and Subprocess calls
        cls.Popen = MockPopen()
        cls.Popen.set_default(stdout=b"")
        cls.replacer = Replacer()
        cls.replacer.replace("subprocess.Popen", cls.Popen)
        cls.replacer.replace("odev.common.bash.Popen", cls.Popen)
        cls.addClassCleanup(cls.replacer.restore)
        return super().setUpClass()
