"""Arguments parsing actions"""

from argparse import Action, ArgumentParser, Namespace
from typing import Optional, Sequence, Union


class CommaSplitAction(Action):
    """
    Converter for command line arguments passed as comma-separated lists of values
    """

    def __call__(
        self,
        parser: ArgumentParser,
        namespace: Namespace,
        values: Union[str, Sequence, None],
        option_string: Optional[str] = None,
    ) -> None:
        values = values.split(",") if isinstance(values, str) else values
        setattr(namespace, self.dest, values)


class OptionalStringAction(Action):
    """
    Converter for command line arguments passed as an optional single string
    """

    def __call__(
        self,
        parser: ArgumentParser,
        namespace: Namespace,
        values: Union[str, Sequence, None],
        option_string: Optional[str] = None,
    ) -> None:
        setattr(namespace, self.dest, values[0] if isinstance(values, list) and len(values) else values)
