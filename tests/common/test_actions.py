import re
from argparse import Namespace

from odev.common.actions import CommaSplitAction, RegexAction


class TestCommonActions:
    def setup_method(self):
        """Create a new namespace for each test."""
        self.namespace = Namespace()

    def test_comma_split_action(self):
        """A comma-separated list of values should be converted to a list."""
        assert CommaSplitAction._action_name() == "store_comma_split", "should have the correct action name"
        action = CommaSplitAction([], "test")

        action(None, self.namespace, None)
        assert self.namespace.test is None, "should keep None as None"

        action(None, self.namespace, "a,b,c")
        assert self.namespace.test == ["a", "b", "c"], "should convert a comma-separated string to a list"

        action(None, self.namespace, ["a,b", "c"])
        assert self.namespace.test == [
            ["a", "b"],
            ["c"],
        ], "should convert a list of comma-separated strings to a list of lists"

    def test_regex_action(self):
        """A string should be converted to a compiled regex."""
        assert RegexAction._action_name() == "store_regex", "should have the correct action name"
        action = RegexAction([], "test")

        action(None, self.namespace, None)
        assert self.namespace.test is None, "should keep None as None"

        action(None, self.namespace, "a")
        assert self.namespace.test == re.compile("a"), "should convert a string to a regular expression"

        action(None, self.namespace, ["a", "b"])
        assert self.namespace.test == [
            re.compile("a"),
            re.compile("b"),
        ], "should convert a list of strings to a list of regular expressions"
