from getpass import getpass
from typing import Optional, Union, Sequence, List

from ..log import term


__all__ = [
    "format_question",
    "confirm",
    "ask",
    "password",
]


interactive: bool = True


def format_question(
    question: str,
    choices: Optional[Union[str, Sequence[str]]] = None,
    default: Optional[str] = None,
    trailing: str = " ",
    choices_sep: str = "/",
) -> str:
    text_parts: List[str] = [term.bright_magenta("[?]"), question]
    if isinstance(choices, (list, tuple)):
        choices = choices_sep.join(choices)
    if choices:
        text_parts.append(f"[{choices}]")
    if default:
        text_parts.append(f"({default})")
    return " ".join(text_parts) + trailing


def confirm(question: str) -> bool:
    """
    Asks the user to enter Y or N (case-insensitive).
    """
    if not interactive:
        return True
    choices = ["y", "n"]
    answer: str = ""
    while answer not in choices:
        answer = input(format_question(question, choices=choices))[0].lower()
    return answer == "y"


def ask(question: str, default: Optional[str] = None) -> str:
    """
    Asks something to the user.
    """
    if not interactive:
        raise RuntimeError(
            f"Cannot prompt for input while running non interactively:\n{question}"
        )
    answer: str = input(format_question(question, default=default))
    if default and not answer:
        return default
    return answer


def password(question: str):
    """
    Asks for a password.
    """
    if not interactive:
        raise RuntimeError(
            f"Cannot prompt for password while running non interactively:\n{question}"
        )
    return getpass(format_question(question))
