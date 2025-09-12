import importlib
import shutil
from pathlib import Path
from typing import (
    Any,
    Callable,
    ClassVar,
    List,
    Optional,
    Tuple,
)
from unittest import TestCase
from unittest.mock import PropertyMock, _patch, patch

from testfixtures import Replacer

from odev.common import odev
from odev.common.string import suid
from tests.fixtures import CaptureOutput


class OdevTestCase(TestCase):
    """Base test class for Odev structures and commands."""

    odev: ClassVar["odev.Odev"]
    """The Odev instance used for the tests."""

    run_id: ClassVar[str]
    """Unique identifier for the test case run."""

    run_name: ClassVar[str]
    """Name of the test case run, used for environment preparation."""

    run_path: ClassVar[Path]
    """Path to the test case run directory under `/tmp`."""

    _patches: ClassVar[List[_patch]] = []
    """The patches applied to the test case."""

    __config: str
    """Content of the configuration file to restore after each test case."""

    def setUp(self):
        self.__check_test_mode()
        self.__save_config()
        self.addCleanup(self.tearDown)

    def tearDown(self):
        self.__restore_config()

    @classmethod
    def setUpClass(cls):
        cls.odev = odev.Odev(test=True)
        cls.run_id = suid()
        cls.run_name = f"{cls.odev.name}-{cls.run_id}"
        cls.run_path = Path(f"/tmp/{cls.run_name}")
        cls.res_path = cls.odev.tests_path / "resources"
        cls.replacer = Replacer()
        cls.__patch_cli()
        cls.__patch_odev()
        cls.__patch_framework()
        cls.addClassCleanup(cls.tearDownClass)
        cls.odev.start()

    @classmethod
    def tearDownClass(cls):
        cls.__unpatch_all()
        cls.replacer.restore()
        cls.odev.commands.clear()
        cls.odev.store.drop()
        cls.odev.config.path.unlink(missing_ok=True)

        if cls.run_path.exists():
            shutil.rmtree(cls.run_path, ignore_errors=True)

    @classmethod
    def patch(cls, target: Any, attribute: str, return_value: Any = None, **kwargs):
        """Patch an object's attribute.
        :param target: The object to patch.
        :param attribute: The name of the attribute to patch.
        :param return_value: The value to return when the attribute is accessed.

        Patch an attribute on an instance:

        >>> with self.patch(self.odev, "prune_databases", return_value=None):
        >>>     ...

        Patch an attribute for all instances of a class, selected by import path:

        >>> with self.patch("odev.common.connectors.PostgresConnector", "query", []):
        >>>     ...
        """
        if isinstance(target, str):
            return patch(f"{target}.{attribute}", return_value=return_value, **kwargs)
        return patch.object(target, attribute, return_value=return_value, **kwargs)

    @classmethod
    def patch_property(cls, target: Any, attribute: str, value: Any, **kwargs):
        """Patch an object's property.
        :param target: The object to patch.
        :param attribute: The name of the property to patch.
        :param value: The value to return when the property is accessed.
        """
        if isinstance(target, str):
            return patch(f"{target}.{attribute}", new_callable=PropertyMock, return_value=value, **kwargs)
        return patch.object(target, attribute, new_callable=PropertyMock, return_value=value, **kwargs)

    @classmethod
    def wrap(cls, target: Any, attribute: str, wrapper: Optional[Callable[..., Any]] = None, **kwargs):
        """Wrap an object's attribute with a function, making it registering calls during tests while keeping
        its original behavior.
        :param target: The object to wrap.
        :param attribute: The name of the attribute to wrap.
        :param wrapper: The function to wrap the attribute with.
        """
        if wrapper is None:
            wrapper = cls._import_dotted_path(f"{target if isinstance(target, str) else target.__module__}.{attribute}")

            if not callable(wrapper):
                raise ValueError("Wrapper must be a callable")

        return cls.patch(target, attribute, side_effect=wrapper, **kwargs)

    @classmethod
    def _import_dotted_path(cls, path: str) -> Any:
        """Import an object from a dotted path."""
        attributes: List[str] = []
        max_iterations = path.count(".")

        while len(attributes) <= max_iterations:
            try:
                imported = importlib.import_module(path)

                for attribute in attributes[::-1]:
                    if not hasattr(imported, attribute):
                        raise AttributeError(f"Attribute {attribute} not found in path {path}")

                    imported = getattr(imported, attribute)

                return imported

            except ModuleNotFoundError:
                parts = path.split(".")
                path = ".".join(parts[:-1])
                attributes += parts[-1:]

    @classmethod
    def __unpatch_all(cls):
        for patched in cls._patches:
            patched.stop()

    @classmethod
    def _patch_object(
        cls,
        target: Any,
        attributes: Optional[List[Tuple[str, Any]]] = None,
        properties: Optional[List[Tuple[str, Any]]] = None,
        **kwargs,
    ):
        """Patch an object's attributes and properties.
        :param target: The object to patch.
        :param attributes: A list of tuples with the attribute name and value to patch.
        :param properties: A list of tuples with the property name and value to patch.
        """
        for attribute, value in attributes or []:
            patched = cls.patch(target, attribute, return_value=value, **kwargs)
            cls._patches.append(patched)
            patched.start()

        for attribute, value in properties or []:
            patched = cls.patch_property(target, attribute, value, **kwargs)
            cls._patches.append(patched)
            patched.start()

    @classmethod
    def __patch_cli(cls):
        """Patch interactions with the CLI to avoid waiting for user input or showing live status during tests."""
        cls._patch_object("odev.common.console.Console", properties=[("bypass_prompt", True)])
        cls._patch_object("odev.common.debug", [("DEBUG_MODE", True)])
        cls._patch_object("odev.common.progress", [("DEBUG_MODE", True)])

    @classmethod
    def __patch_framework(cls):
        """Patch the framework across all of odev to use the test environment."""
        patch_paths = [
            "odev.common.mixins.framework.framework.OdevFrameworkMixin",
            "odev.common.connectors.base.Connector",
        ]

        for path in patch_paths:
            cls._patch_object(path, properties=[("odev", cls.odev)])

    @classmethod
    def __patch_odev(cls):
        """Patch framework low-level features that could conflict with the tests execution."""
        odev.HOME_PATH = cls.run_path

        cls._patch_object(
            odev.Odev,
            [
                ("prune_databases", None),
                ("_update", False),
            ],
            [
                ("name", "odev-test"),
                ("upgrades_path", cls.odev.tests_path / "resources" / "upgrades"),
                ("setup_path", cls.odev.tests_path / "resources" / "setup"),
                ("scripts_path", cls.odev.tests_path / "resources" / "scripts"),
            ],
        )

    def __check_test_mode(self):
        self.assertTrue(self.odev.in_test_mode, "Odev is not in test mode, failing test to prevent accidental damage")

    def __save_config(self):
        with self.odev.config.path.open("r") as config:
            self.__config = config.read()

    def __restore_config(self):
        with self.odev.config.path.open("w") as config:
            config.write(self.__config)

        self.odev.config.load()


class OdevCommandTestCase(OdevTestCase):
    """Extended test case to run commands in test mode."""

    def dispatch_command(self, command: str, *arguments: str) -> Tuple[str, str]:
        """Run a command with arguments.
        :param command: The name of the command to run.
        :param arguments: The arguments to pass to the command, as if they where received through the CLI.
        :return The captured stdout and stderr of the command.
        """
        with CaptureOutput() as output:
            self.odev.dispatch([self.odev.name, command, *arguments])

        return output.stdout, output.stderr
