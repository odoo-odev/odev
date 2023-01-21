from argparse import Namespace

from odev.common.actions import CommaSplitAction, OptionalStringAction


class TestCommonActions:
    def setup_method(self):
        """Create a new namespace for each test."""
        self.namespace = Namespace()

    def test_comma_split_action(self):
        """A comma-separated list of values should be converted to a list."""
        action = CommaSplitAction([], "test")

        action(None, self.namespace, "a,b,c")
        assert self.namespace.test == ["a", "b", "c"], "should convert a comma-separated string to a list"

        action(None, self.namespace, ["a", "b", "c"])
        assert self.namespace.test == ["a", "b", "c"], "should keep a list as a list"

    def test_optional_string_action(self):
        """A single string should be converted to a list."""
        action = OptionalStringAction([], "test")

        action(None, self.namespace, "a")
        assert self.namespace.test == "a", "should keep a single string as a string"

        action(None, self.namespace, ["a", "b"])
        assert self.namespace.test == "a", "should convert the first element of a list to a string"

        action(None, self.namespace, None)
        assert self.namespace.test is None, "should keep an empty value as empty"
