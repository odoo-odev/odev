import importlib
import shutil
from collections.abc import Callable
from configparser import ConfigParser
from pathlib import Path
from typing import (
    Any,
    ClassVar,
)
from unittest import TestCase
from unittest.mock import PropertyMock, _patch, patch

from testfixtures import Replacer

from odev.common import odev
from odev.common.config import Config
from odev.common.string import suid

from tests.fixtures import CaptureOutput, sandbox


class OdevTestCase(TestCase):
    """Base test class for Odev structures and commands."""

    odev: ClassVar["odev.Odev"]
    """The Odev instance used for the tests."""

    run_id: ClassVar[str]
    """Unique identifier for the test case run."""

    run_name: ClassVar[str]
    """Name of the test case run, used for environment preparation."""

    run_path: ClassVar[Path]
    """Path to the test case run directory, inside the sandbox of the current suite run."""

    _patches: ClassVar[list[_patch]]
    """The patches applied to the test case.

    Assigned per class in `setUpClass`: a list defined here would be shared by every subclass through
    `cls._patches.append(...)`, making each class tear down the patches of all the classes before it.
    """

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
        cls._patches = []
        cls.run_id = suid()
        cls.run_path = sandbox.SESSION_PATH / cls.run_id
        cls.run_name = f"{sandbox.SESSION_NAME}-{cls.run_id}"

        # The framework reads its name and its configuration directory while being constructed, so both
        # have to point inside the sandbox before the instance exists.
        cls.__patch_paths()

        Config.parser = ConfigParser()
        cls.odev = odev.Odev(test=True, name=sandbox.SESSION_NAME)
        cls.res_path = cls.odev.tests_path / "resources"
        cls.replacer = Replacer()
        cls.__patch_cli()
        cls.__patch_odev()
        cls.__patch_framework()
        cls.addClassCleanup(cls.tearDownClass)
        cls.odev.start()
        cls.__sandbox_config_paths()

    @classmethod
    def tearDownClass(cls):
        cls.__unpatch_all()
        cls.replacer.restore()
        cls.odev.commands.clear()
        cls.odev.store.drop()

        # The configuration file lives in the run directory, and goes away with it. Whatever this misses,
        # because the run was interrupted or because a test left a database behind, is picked up by the
        # sandbox: either when the suite ends or at the start of the next one.
        shutil.rmtree(cls.run_path, ignore_errors=True)

        odev.HOME_PATH = (Path.home() / ".local" / "share" / "odev").resolve()

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
    def wrap(cls, target: Any, attribute: str, wrapper: Callable[..., Any] | None = None, **kwargs):
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
        attributes: list[str] = []
        max_iterations = path.count(".")

        while len(attributes) <= max_iterations:
            try:
                imported = importlib.import_module(path)

                for attribute in attributes[::-1]:
                    if not hasattr(imported, attribute):
                        raise AttributeError(f"Attribute {attribute} not found in path {path}")

                    imported = getattr(imported, attribute)

            except ModuleNotFoundError:
                parts = path.split(".")
                path = ".".join(parts[:-1])
                attributes += parts[-1:]

            else:
                return imported

        return None

    @classmethod
    def __unpatch_all(cls):
        # `tearDownClass` runs twice, once through `addClassCleanup` and once through unittest itself,
        # so the patches are dropped as they are stopped.
        while cls._patches:
            cls._patches.pop().stop()

    @classmethod
    def _patch_object(
        cls,
        target: Any,
        attributes: list[tuple[str, Any]] | None = None,
        properties: list[tuple[str, Any]] | None = None,
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
    def __patch_paths(cls):
        """Redirect the configuration directory into the run directory.

        The config file, and the plugin `config.py` modules `Config` discovers next to it, then come from
        the sandbox instead of `~/.config/odev`: the suite writes nothing outside of it, and behaves the
        same whether or not the developer running it has plugins installed.
        """
        patched = patch("odev.common.config.CONFIG_DIR", cls.run_path)
        cls._patches.append(patched)
        patched.start()

    @classmethod
    def __sandbox_config_paths(cls):
        """Point the directories odev reads from its configuration at the sandbox.

        They default to `~/odoo`, where a test cloning a repository or downloading a dump would land in
        the middle of the checkouts of the user — and in the way of a suite running alongside this one.
        """
        cls.odev.config.paths.repositories = cls.run_path / "repositories"
        cls.odev.config.paths.dumps = cls.run_path / "dumps"
        cls.odev.config.paths.upgrade = cls.run_path / "repositories" / "odoo" / "upgrade"

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
                ("upgrades_path", cls.odev.tests_path / "resources" / "upgrades"),
                ("setup_path", cls.odev.tests_path / "resources" / "setup"),
                ("scripts_path", cls.odev.tests_path / "resources" / "scripts"),
                ("plugins_path", cls.run_path / "plugins"),
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

    def dispatch_command(self, command: str, *arguments: str) -> tuple[str, str]:
        """Run a command with arguments.
        :param command: The name of the command to run.
        :param arguments: The arguments to pass to the command, as if they where received through the CLI.
        :return The captured stdout and stderr of the command.
        """
        with CaptureOutput() as output:
            self.odev.dispatch([self.odev.name, command, *arguments])

        return output.stdout, output.stderr
