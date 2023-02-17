"""Shared methods for working with strings."""

import random
import string as string_module
import textwrap
from typing import List, Tuple, Union


def normalize_indent(text: str) -> str:
    """Normalize the indentation of a string.

    :param text: The text to normalize.
    :return: The normalized text.
    :rtype: str
    """
    if "\n" in text:
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
    return f"[bold]{name}[/bold]{help_text}"


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
    :return: The dedented text.
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
    :param suffix: The suffix to add to the number.
    :return: The formatted number.
    :rtype: str
    """
    for unit in ["", "K", "M", "G", "T", "P", "E", "Z"]:
        if abs(size) < 1024.0:
            return f"{size:3.1f} {unit}B"
        size /= 1024.0
    return f"{size:.1f} YB"


def suid() -> str:
    """Return a randomly generated unique identifier.

    :return: The unique identifier.
    :rtype: str
    """
    alphabet = string_module.ascii_lowercase + string_module.digits
    return "".join(random.choices(alphabet, k=8))
