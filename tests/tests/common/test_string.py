import datetime

from odev.common import string

from tests.fixtures import OdevTestCase


class TestCommonStringSizes(OdevTestCase):
    """Byte sizes should be formatted and parsed back consistently."""

    def test_01_bytes_size_units(self):
        """Sizes should be scaled down to the largest unit under the 1024 factor."""
        self.assertEqual(string.bytes_size(0), "0.0 B")
        self.assertEqual(string.bytes_size(512), "512.0 B")
        self.assertEqual(string.bytes_size(1024), "1.0 KB")
        self.assertEqual(string.bytes_size(1024**2), "1.0 MB")
        self.assertEqual(string.bytes_size(1536**2), "2.2 MB")
        self.assertEqual(string.bytes_size(1024**3), "1.0 GB")

    def test_02_bytes_size_largest_unit(self):
        """Sizes above the largest known unit should fall back to yottabytes."""
        self.assertEqual(string.bytes_size(1024**8), "1.0 YB")
        self.assertEqual(string.bytes_size(1024**9), "1024.0 YB")

    def test_03_bytes_size_negative(self):
        """Negative sizes should be scaled on their absolute value and keep their sign."""
        self.assertEqual(string.bytes_size(-1024), "-1.0 KB")

    def test_04_bytes_from_string(self):
        """Human readable sizes should be converted back to a number of bytes."""
        self.assertEqual(string.bytes_from_string("512"), 512)
        self.assertEqual(string.bytes_from_string("512 B"), 512)
        self.assertEqual(string.bytes_from_string("1 KB"), 1024)
        self.assertEqual(string.bytes_from_string("1.5 MB"), 1572864)
        self.assertEqual(string.bytes_from_string("2GB"), 2 * 1024**3)

    def test_05_bytes_from_string_invalid(self):
        """A representation not starting with a number cannot be parsed."""
        with self.assertRaises(ValueError):
            string.bytes_from_string("not a size")

    def test_06_bytes_size_roundtrip(self):
        """Formatting a size and parsing it back should return the original value."""
        for size in (1024, 4 * 1024**2, 3 * 1024**3):
            self.assertEqual(string.bytes_from_string(string.bytes_size(size)), size)


class TestCommonStringIndent(OdevTestCase):
    """Indentation helpers back the layout of the `help` command output."""

    text = "    first line\n        nested line\n    last line"

    def test_01_min_indent(self):
        """The smallest indentation of all non-blank lines should be returned."""
        self.assertEqual(string.min_indent(self.text), 4)
        self.assertEqual(string.min_indent("no indent"), 0)

    def test_02_min_indent_without_content(self):
        """A text without any non-blank line has no indentation to measure."""
        self.assertEqual(string.min_indent(""), 0)
        self.assertEqual(string.min_indent("\n\n"), 0)
        self.assertEqual(string.min_indent("   \n\t\n  "), 0)

    def test_03_indent(self):
        """Indenting should prefix every line with the requested number of spaces."""
        self.assertEqual(string.indent("one\ntwo", 2), "  one\n  two")
        self.assertEqual(string.indent("one\ntwo"), "one\ntwo")

    def test_04_dedent(self):
        """Dedenting by zero should keep the text as-is, relative indentation included."""
        self.assertEqual(string.dedent(self.text), self.text)

    def test_05_dedent_removes_indentation(self):
        """Dedenting should remove the requested number of spaces from every line."""
        self.assertEqual(string.dedent(self.text, 4), "first line\n    nested line\nlast line")

    def test_06_dedent_without_content(self):
        """Dedenting a blank text should not fail on the absence of a minimum indentation."""
        self.assertEqual(string.dedent(""), "")
        self.assertEqual(string.dedent("\n\n"), "\n\n")

    def test_07_normalize_indent(self):
        """Normalizing should clean up a docstring-like text and strip its surrounding blanks."""
        self.assertEqual(string.normalize_indent("\n    first line\n    second line\n    "), "first line\nsecond line")
        self.assertEqual(string.normalize_indent(""), "")


class TestCommonStringJoin(OdevTestCase):
    """Parts should be joined with the delimiters expected in user-facing messages."""

    def test_01_join(self):
        """Parts should be joined with commas when no last delimiter is given."""
        self.assertEqual(string.join([]), "")
        self.assertEqual(string.join(["one"]), "one")
        self.assertEqual(string.join(["one", "two", "three"]), "one, two, three")

    def test_02_join_and(self):
        """The last two parts should be separated by "and"."""
        self.assertEqual(string.join_and([]), "")
        self.assertEqual(string.join_and(["one"]), "one")
        self.assertEqual(string.join_and(["one", "two"]), "one and two")
        self.assertEqual(string.join_and(["one", "two", "three"]), "one, two and three")

    def test_03_join_or(self):
        """The last two parts should be separated by "or"."""
        self.assertEqual(string.join_or(["one", "two", "three"]), "one, two or three")

    def test_04_join_bullet(self):
        """Parts should be listed as bullets, without a leading blank line."""
        self.assertEqual(string.join_bullet([]), "")
        self.assertEqual(string.join_bullet(["one"]), "• one")
        self.assertEqual(string.join_bullet(["one", "two"]), "• one\n• two")


class TestCommonStringQuote(OdevTestCase):
    """Quoting picks a delimiter absent from the string, it never escapes."""

    def test_01_quote_default(self):
        """A string without quotes should be wrapped in double quotes."""
        self.assertEqual(string.quote("plain"), '"plain"')

    def test_02_quote_containing_single(self):
        """A string containing single quotes should be wrapped in double quotes."""
        self.assertEqual(string.quote("it's"), '"it\'s"')

    def test_03_quote_containing_double(self):
        """A string containing double quotes should be wrapped in single quotes."""
        self.assertEqual(string.quote('say "hi"'), "'say \"hi\"'")

    def test_04_quote_force_single(self):
        """Forcing single quotes should win over the automatic delimiter choice."""
        self.assertEqual(string.quote("plain", force_single=True), "'plain'")
        self.assertEqual(string.quote('say "hi"', force_single=True), "'say \"hi\"'")

    def test_05_quote_dirty_only(self):
        """Strings without any quote should be left untouched in `dirty_only` mode."""
        self.assertEqual(string.quote("plain", dirty_only=True), "plain")
        self.assertEqual(string.quote("plain", dirty_only=True, force_single=True), "plain")
        self.assertEqual(string.quote("it's", dirty_only=True), '"it\'s"')

    def test_06_quote_both_quote_characters(self):
        """A string containing both delimiters cannot be represented and falls back to double quotes.

        Documented in `quote`: the helper selects a delimiter and never escapes, so callers must not
        feed it untrusted input.
        """
        self.assertEqual(string.quote("""a'b"c"""), '"a\'b"c"')


class TestCommonStringMarkup(OdevTestCase):
    """Rich markup helpers should produce tags the console can render."""

    def test_01_stylize_resolves_theme_styles(self):
        """Aliased theme styles should be replaced by the value Rich understands."""
        self.assertEqual(string.stylize("text", "bold"), "[bold]text[/bold]")
        self.assertNotIn("color.cyan", string.stylize("text", "color.cyan"))

    def test_02_list_styles(self):
        """Opening tags should be listed in their order of appearance, closing ones ignored."""
        self.assertEqual(string.list_styles("[bold]one[/bold] [color.cyan]two[/color.cyan]"), ["bold", "color.cyan"])
        self.assertEqual(string.list_styles("[bold red]one[/bold red]"), ["bold red"])
        self.assertEqual(string.list_styles("no markup here"), [])

    def test_03_strip_styles(self):
        """Markup tags should be removed, keeping the text they wrap."""
        self.assertEqual(string.strip_styles("[bold]text[/bold]"), "text")
        self.assertEqual(string.strip_styles("plain text"), "plain text")

    def test_04_strip_styles_keeps_nested_tags(self):
        """Only the outermost tag pair is removed, nested markup survives.

        `strip_styles` runs a single non-greedy substitution pass. Nothing in odev calls it today, so the
        limitation is asserted rather than fixed.
        """
        self.assertEqual(
            string.strip_styles("[bold]one [color.cyan]two[/color.cyan] three[/bold]"),
            "one [color.cyan]two[/color.cyan] three",
        )

    def test_05_resolve_styles(self):
        """Aliased styles inside a text should be resolved to their theme value."""
        resolved = string.resolve_styles("[color.cyan]text[/color.cyan]")
        self.assertNotIn("color.cyan", resolved)
        self.assertIn("text", resolved)

    def test_06_strip_ansi_colors(self):
        """ANSI color codes should be removed, leaving the text untouched."""
        self.assertEqual(string.strip_ansi_colors("\x1b[31mred\x1b[0m"), "red")
        self.assertEqual(string.strip_ansi_colors("no colors"), "no colors")

    def test_07_link(self):
        """Links should be rendered with the Rich link markup."""
        self.assertEqual(
            string.link("odev", "https://github.com/odoo-odev"), "[link=https://github.com/odoo-odev]odev[/link]"
        )


class TestCommonStringHelpFormatting(OdevTestCase):
    """Help formatting keeps the descriptions of the `help` command aligned in a column."""

    def test_01_short_help(self):
        """The name should be emphasized and the description aligned after the indentation."""
        self.assertEqual(string.short_help("run", "Run a database"), "[bold]run[/bold] Run a database")
        self.assertEqual(string.short_help("run", "Run a database", 4), "[bold]run[/bold]     Run a database")

    def test_02_format_options_list_aligns_descriptions(self):
        """Descriptions should all start at the same column, driven by the longest name."""
        formatted = string.format_options_list([("run", "Run a database"), ("shell", "Open a shell")])
        descriptions = [line.index("Run a database") for line in formatted.splitlines() if "Run a database" in line]
        descriptions += [line.index("Open a shell") for line in formatted.splitlines() if "Open a shell" in line]

        self.assertEqual(len(set(descriptions)), 1, "descriptions should be aligned on a single column")

    def test_03_format_options_list_blank_lines(self):
        """Blank lines should be inserted between the elements of the list."""
        formatted = string.format_options_list([("run", "Run"), ("shell", "Shell")], blanks=1)
        self.assertEqual(len(formatted.splitlines()), 3)


class TestCommonStringMisc(OdevTestCase):
    """Remaining formatting helpers."""

    def test_01_suid(self):
        """Unique identifiers should be lowercase alphanumeric strings of a fixed length."""
        identifiers = {string.suid() for _ in range(100)}

        for identifier in identifiers:
            self.assertRegex(identifier, r"^[a-z0-9]{8}$")

        self.assertGreater(len(identifiers), 1, "identifiers should not be constant")

    def test_02_seconds_to_time(self):
        """Seconds should be rendered as a hours:minutes:seconds duration."""
        self.assertEqual(string.seconds_to_time(0), "0:00:00")
        self.assertEqual(string.seconds_to_time(3661), "1:01:01")

    def test_03_ago(self):
        """Past datetimes should be rendered relative to now."""
        self.assertEqual(string.ago(datetime.datetime.now() - datetime.timedelta(hours=2)), "2 hours ago")

    def test_04_float_to_hours_drops_minutes(self):
        """Fractions of an hour are lost, minutes always come out as zero.

        `int(value - hours) * 60` truncates the fraction before scaling it, so it can only ever yield 0.
        Nothing in odev nor in the plugins calls this helper, so the behaviour is asserted as-is rather
        than fixed; correcting it would be `int((value - hours) * 60)`.
        """
        self.assertEqual(string.float_to_hours(2.0), "2:00")
        self.assertEqual(string.float_to_hours(1.5), "1:00")
        self.assertEqual(string.float_to_hours(2.25), "2:00")
