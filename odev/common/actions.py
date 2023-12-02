"""Actions for parsing arguments with argparse."""

import re
from abc import ABC, abstractmethod
from argparse import Action as BaseAction, ArgumentParser, Namespace
from ast import literal_eval
from pathlib import Path
from typing import (
    Any,
    List,
    Optional,
    Sequence,
    Union,
)


__all__ = ["ACTIONS_MAPPING"]


class Action(BaseAction, ABC):
    """Base class for custom actions.
    Actions will be available as "store_<action_name>" in the `arguments` mapping
    of a command. The action name is derived from the class name by removing the
    "Action" suffix and converting the camel case to snake case.

    Example:
    >>> class TestAction(Action):
    >>>     ...
    >>>
    >>>
    >>> class MyCommand(Command):
    >>>     arguments = [
    >>>         {
    >>>             "name": "test",
    >>>             "action": "store_test",
    >>>         },
    >>>     ]
    """

    def __call__(
        self,
        parser: ArgumentParser,
        namespace: Namespace,
        values: Union[str, Sequence, None],
        option_string: Optional[str] = None,
    ) -> None:
        setattr(namespace, self.dest, self._transform(values))

    @abstractmethod
    def _transform_one(self, value: str) -> Any:
        """Transform a single value."""

    def _transform(self, values: Union[str, Sequence, None]) -> Optional[Any]:
        """Transform the values passed to the action."""
        if values is None:
            return values

        if isinstance(values, str):
            return self._transform_one(values)

        return [self._transform_one(value) for value in values]

    @classmethod
    def _action_name(cls) -> str:
        """Return the name of the action."""
        return "store_" + re.sub(r"(?<!^)(?=[A-Z])", "_", re.sub(r"Action$", "", cls.__name__)).lower()


class IntAction(Action):
    """Converter for command line arguments passed as a string that should be converted to an int."""

    def _transform_one(self, value: str) -> int:
        return int(value)


class CommaSplitAction(Action):
    """Converter for command line arguments passed as comma-separated lists of values."""

    def _transform_one(self, value: str) -> List[str]:
        return value.split(",")


class RegexAction(Action):
    """Converter for command line arguments passed as a string that should be compiled as a regex."""

    def _transform_one(self, value: str) -> re.Pattern[str]:
        return re.compile(value)


class PathAction(Action):
    """Converter for command line arguments passed as a string that should be converted to a Path."""

    def _transform_one(self, value: str) -> Path:
        return Path(value)


class EvalAction(Action):
    """Converter for command line arguments passed as a string that should be evaluated to literals."""

    def _transform_one(self, value: str) -> Any:
        return literal_eval(value)


ACTIONS_MAPPING = {a._action_name(): a for a in Action.__subclasses__()}
