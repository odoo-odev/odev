import re
from argparse import Namespace

from odev.common.actions import CommaSplitAction, RegexAction
from tests.fixtures import OdevTestCase


class TestCommonActions(OdevTestCase):
    def setUp(self):
        """Create a new namespace for each test."""
        self.namespace = Namespace()

    def test_comma_split_action(self):
        """A comma-separated list of values should be converted to a list."""
        self.assertEqual(CommaSplitAction._action_name(), "store_comma_split", "should have the correct action name")
        action = CommaSplitAction([], "test")

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
