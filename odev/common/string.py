"""Shared methods for working with strings."""

import datetime
import random
import re
import string as string_module
import textwrap
from typing import (
    List,
    Optional,
    Sequence,
    Tuple,
    Union,
)

import timeago  # type: ignore [import]


__all__ = [
    "bytes_from_string",
    "bytes_size",
    "dedent",
    "format_options_list",
    "indent",
    "min_indent",
    "normalize_indent",
    "short_help",
    "suid",
]


def normalize_indent(text: str) -> str:
    """Normalize the indentation of a string.

    :param text: The text to normalize.
    :return: The normalized text.
    :rtype: str
    """
    if "\n" in text.strip():
        min_indent = min(len(line) - len(line.lstrip()) for line in text.splitlines()[1:] if line.strip())
        text = " " * min_indent + text
    return textwrap.dedent(text).strip()


def short_help(name: str, description: str, indent_len: int = 0) -> str:
    """Return the short help formatted for a name and its description.

    :param name: The name of the element.
    :param description: The description of the element.
    :param indent_len: The number of spaces to indent the help.
    :return: The short help of the element.
    :rtype: str
    """
    help_text = indent(description, indent_len + 4)[len(name) :]
    return stylize(name, "bold") + help_text


def format_options_list(elements: List[Tuple[str, str]], indent_len: int = 0, blanks: int = 0) -> str:
    """Return a list of elements formatted as a string.

    :param elements: The list of elements to format.
        A list of tuples containing the name of the element and its description.
    :param indent: The number of spaces to indent the list.
    :param blanks: The number of blank lines to add between elements of the list.
    :return: The list of elements formatted as a string.
    :rtype: str
    """
    elements_indent = max(len(element[0]) for element in elements)
    elements_list: str = ("\n" * (blanks + 1)).join([short_help(*element, elements_indent) for element in elements])
    return indent(elements_list, indent_len + 4)[indent_len:]


def indent(text: str, indent: int = 0) -> str:
    """Indent a text.

    :param text: The text to indent.
    :param indent: The number of spaces to indent the text.
    :return: The indented text.
    :rtype: str
    """
    return textwrap.indent(text, " " * indent)


def dedent(text: str, dedent: int = 0) -> str:
    """Dedent a text.

    :param text: The text to dedent.
    :param dedent: The number of spaces to dedent the text.
    :return: The un-indented text.
    :rtype: str
    """
    return indent(textwrap.dedent(text), min_indent(text) - dedent)


def min_indent(text: str) -> int:
    """Return the smallest indentation in a text.

    :param text: The text to get the minimum indentation from.
    :return: The minimum indentation of the text.
    :rtype: int
    """
    return min(len(line) - len(line.lstrip()) for line in text.splitlines() if line.strip())


def bytes_size(size: Union[int, float]) -> str:
    """Formats a number to its human readable representation in bytes-units.

    :param size: The number to format.
    :return: The formatted number.
    :rtype: str
    """
    for unit in ["", "K", "M", "G", "T", "P", "E", "Z"]:
        if abs(size) < 1024.0:
            return f"{size:3.1f} {unit}B"
        size /= 1024.0
    return f"{size:.1f} YB"


def bytes_from_string(string: str) -> int:
    """Converts a human readable representation of bytes-units to a number.

    :param repr: The string to parse.
    :return: The number of bytes.
    :rtype: str
    """
    match = re.match(r"(?P<number>\d+(?:\.\d+)?)\s*(?P<factor>[KMGTPEZY]?)(?P<unit>B|b)?", string)

    if not match:
        raise ValueError(f"Invalid bytes representation: {string}")

    number = float(match.group("number"))
    factor = 1024.0 ** ["", "K", "M", "G", "T", "P", "E", "Z", "Y"].index(match.group("factor"))
    return int(number * factor)


def suid() -> str:
    """Return a randomly generated unique identifier.

    :return: The unique identifier.
    :rtype: str
    """
    alphabet = string_module.ascii_lowercase + string_module.digits
    return "".join(random.choices(alphabet, k=8))


def stylize(value: str, style: str) -> str:
    """Stylize a value to use with Rich markup.
    :param value: The value to stylize.
    :param style: The style to apply.
    :return: The stylized value.
    :rtype: str
    """
    from odev.common.console import resolve_styles

    style = resolve_styles(style)
    return f"[{style}]{value}[/{style}]"


def strip_styles(text: str) -> str:
    """Strip Rich styles from a text, returning its raw content without markup.
    :param text: The text to strip styles from.
    """
    return re.sub(r"\[(\w+(\.\w+)*(\s+\w+)*)\](.*?)\[\/\1\]", r"\4", text)


def resolve_styles(text: str) -> str:
    """Resolve markup styles from a text, replacing aliased styles by their proper value usable by Rich.
    :param text: The text to resolve styles from.
    """
    from odev.common.console import resolve_styles

    def replace_tag(match: re.Match) -> str:
        tag = f"{match.group(1)} {replacement} {match.group(2)}".strip()
        return stylize(match.group(3), tag)

    for style in list_styles(text):
        replacement = resolve_styles(style)
        tag = re.escape(style)
        text = re.sub(rf"\[(.*?)(?:{tag})(.*?)\](.*?)\[\/\1(?:{tag})\2\]", replace_tag, text)

    return text


def list_styles(text: str) -> List[str]:
    """Extract Rich styles from a text and returns the list of tags in their order of appearance.
    Only lists unique opening tags, closing tags are ignored. Nested tags are supported.
    :param text: The text to list styles from.
    """
    return re.findall(r"\[(?!\/)([\w\.]+(?:\s+[\w\.]+)*)\]", text)


def strip_ansi_colors(text: str) -> str:
    """Strip ANSI colors from a text, leave other control characters and escape codes.
    :param text: The text to strip color codes from.
    """
    return re.sub(r"\x1b[^m]*m", "", text)


def join(parts: Sequence[str], last_delimiter: Optional[str] = None) -> str:
    """Join parts, optionally adding a last delimiter between the last two items.
    :param parts: Parts to join.
    :param last_delimiter: The last delimiter to add.
    :return: The joined parts.
    :rtype: str
    """
    if not parts:
        return ""

    if len(parts) == 1:
        return parts[0]

    if last_delimiter is None:
        return ", ".join(parts)

    return ", ".join(parts[:-1]) + f" {last_delimiter} {parts[-1]}"


def join_and(parts: Sequence[str]) -> str:
    """Join parts adding "and" between the two lasts items.
    :param parts: Parts to join.
    :return: The joined parts.
    :rtype: str
    """
    return join(parts, "and")


def join_or(parts: Sequence[str]) -> str:
    """Join parts adding "or" between the two lasts items.
    :param parts: Parts to join.
    :return: The joined parts.
    :rtype: str
    """
    return join(parts, "or")


def join_bullet(parts: Sequence[str]) -> str:
    """Join parts as a bullet list.
    :param parts: Parts to join.
    :return: The joined parts.
    :rtype: str
    """
    bullet = "\n•"
    return "".join([f"{bullet} {part}" for part in parts]).strip()


def seconds_to_time(seconds: int) -> str:
    """Convert seconds to a human readable time.
    :param seconds: The number of seconds.
    :return: The human readable time.
    :rtype: str
    """
    return str(datetime.timedelta(seconds=seconds))


def ago(date: datetime.datetime) -> str:
    """Return a human readable representation of a datetime to show how long ago it was.
    :param date: The datetime to convert.
    :return: The human readable representation.
    :rtype: str
    """
    return timeago.format(date, datetime.datetime.utcnow())


def quote(string: str, dirty_only: bool = False, force_single: bool = False) -> str:
    """Quote a string.
    :param string: The string to quote.
    :param dirty_only: Do not quote strings that have no quotes to begin with.
    :param force_single: Force single quotes.
    :return: The quoted string.
    :rtype: str
    """
    index = max(string.find(char) for char in {"'", '"'})

    if dirty_only and index == -1:
        return string

    double = not force_single and (index == -1 or string[index] == "'")
    return f'"{string}"' if double else f"'{string}'"
