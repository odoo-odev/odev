import re
from argparse import Namespace
from pathlib import Path

from odev.common.actions import IntAction, ListAction, RegexAction, PathAction, EvalAction
from tests.fixtures import OdevTestCase


class TestCommonActions(OdevTestCase):
    def setUp(self):
        """Create a new namespace for each test."""
        self.namespace = Namespace()

    def test_int_action(self):
        """A string should be converted to an integer."""
        self.assertEqual(IntAction._action_name(), "store_int", "should have the correct action name")
        action = IntAction([], "test")

        action(None, self.namespace, None)
        self.assertIsNone(self.namespace.test, "should keep None as None")

        action(None, self.namespace, "10")
        self.assertEqual(self.namespace.test, 10, "should convert a string to an integer")

        action(None, self.namespace, ["10", "20"])
        self.assertListEqual(self.namespace.test, [10, 20], "should convert a list of strings to a list of integers")

        with self.assertRaises(ValueError, msg="should raise an error if the string is not a number"):
            action(None, self.namespace, "a")

    def test_list_action(self):
        """A comma-separated list of values should be converted to a list."""
        self.assertEqual(ListAction._action_name(), "store_list", "should have the correct action name")
        action = ListAction([], "test")

        action(None, self.namespace, None)
        self.assertIsNone(self.namespace.test, "should keep None as None")

        action(None, self.namespace, "a,b,c")
        self.assertListEqual(self.namespace.test, ["a", "b", "c"], "should convert a comma-separated string to a list")

        action(None, self.namespace, ["a,b", "c"])
        self.assertListEqual(
            self.namespace.test,
            [
                ["a", "b"],
                ["c"],
            ],
            "should convert a list of comma-separated strings to a list of lists",
        )

    def test_regex_action(self):
        """A string should be converted to a compiled regex."""
        self.assertEqual(RegexAction._action_name(), "store_regex", "should have the correct action name")
        action = RegexAction([], "test")

        action(None, self.namespace, None)
        self.assertIsNone(self.namespace.test, "should keep None as None")

        action(None, self.namespace, "a")
        self.assertEqual(self.namespace.test, re.compile("a"), "should convert a string to a regular expression")

        action(None, self.namespace, ["a", "b"])
        self.assertListEqual(
            self.namespace.test,
            [
                re.compile("a"),
                re.compile("b"),
            ],
            "should convert a list of strings to a list of regular expressions",
        )

        with self.assertRaises(ValueError, msg="should raise an error if the regex is invalid"):
            action(None, self.namespace, "a(")

    def test_path_action(self):
        """A string should be converted to a Path object."""
        self.assertEqual(PathAction._action_name(), "store_path", "should have the correct action name")
        action = PathAction([], "test")

        action(None, self.namespace, None)
        self.assertIsNone(self.namespace.test, "should keep None as None")

        action(None, self.namespace, ".")
        self.assertEqual(self.namespace.test, Path(".").resolve(), "should convert a string to a Path object")

        action(None, self.namespace, ["a", "b"])
        self.assertListEqual(
            self.namespace.test,
            [
                Path("a").resolve(),
                Path("b").resolve(),
            ],
            "should convert a list of strings to a list of Path objects",
        )

    def test_eval_action(self):
        """A string should be converted to a python literal."""
        self.assertEqual(EvalAction._action_name(), "store_eval", "should have the correct action name")
        action = EvalAction([], "test")

        action(None, self.namespace, None)
        self.assertIsNone(self.namespace.test, "should keep None as None")

        action(None, self.namespace, "10")
        self.assertEqual(self.namespace.test, 10, "should convert digits string to an integer")

        action(None, self.namespace, "['a', 'b']")
        self.assertListEqual(self.namespace.test, ["a", "b"], "should convert a string to a list")

        action(None, self.namespace, "{'a': 1, 'b': 'c'}")
        self.assertDictEqual(self.namespace.test, {"a": 1, "b": "c"}, "should convert a string to a dictionary")

        with self.assertRaises(ValueError, msg="should raise an error if the string is invalid"):
            action(None, self.namespace, "a(")
