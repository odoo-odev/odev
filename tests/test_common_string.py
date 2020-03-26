from odev.common import string
from tests.fixtures import OdevTestCase


class TestCommonString(OdevTestCase):
    def test_normalize_indent(self):
        """String should be normalized."""
        expected = "test line 1\n    line 2\nline 3"
        assert (
            string.normalize_indent("test line 1\n          line 2\n      line 3") == expected
        ), "indent should be normalized"

    def test_format_options_list(self):
        """Options list should be formatted."""
        expected = "    [bold]test[/bold]    test2"
        assert string.format_options_list([("test", "test2")]) == expected, "options list should be formatted"

    def test_indent(self):
        """String should be indented."""
        assert string.indent("text", 4) == "    text", "string should be indented"

    def test_dedent(self):
        """String should be dedented."""
        assert string.dedent("    text", 4) == "text", "string should be dedented"
