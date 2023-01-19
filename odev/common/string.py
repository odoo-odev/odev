"""Shared methods for working with strings."""

import textwrap
from typing import List, Tuple


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
    min_indent = min(len(line) - len(line.lstrip()) for line in text.splitlines() if line.strip())
    return indent(textwrap.dedent(text), min_indent - dedent)
