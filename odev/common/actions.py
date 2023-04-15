"""Actions for parsing arguments with argparse."""

import re
from abc import ABC, abstractmethod
from argparse import Action as BaseAction, ArgumentParser, Namespace
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
    """Base class for custom actions."""

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


ACTIONS_MAPPING = {a._action_name(): a for a in Action.__subclasses__()}
