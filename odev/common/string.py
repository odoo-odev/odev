"""Shared methods for working with strings."""

import textwrap


def normalize_indent(text: str) -> str:
    """Normalize the indentation of a string.

    :param text: The text to normalize.
    :return: The normalized text.
    :rtype: str
    """
    if "\n" in text:
        indent = min(len(line) - len(line.lstrip()) for line in text.splitlines()[1:] if line.strip())
        text = " " * indent + text
    return textwrap.dedent(text).strip()
