"""Metaclass for keeping track of the order in which class members are declared.

See: https://peps.python.org/pep-3115/#example
"""

from abc import ABCMeta
from typing import Any, cast


class MemberTable(dict):
    """A dictionary which keeps track of the order in which keys are added."""

    def __init__(self):
        self.member_names: list = []

    def __setitem__(self, key: str, value: Any):
        if key not in self:
            self.member_names.append(key)

        dict.__setitem__(self, key, value)


class OrderedClassAttributes(ABCMeta):
    """Metaclass which creates a list of the names of all class members, in the order that they were declared."""

    member_names: list

    @classmethod
    def __prepare__(cls, name, bases):
        return MemberTable()

    def __new__(cls, name, bases, classdict) -> ABCMeta:
        result = ABCMeta.__new__(cls, name, bases, dict(classdict))
        result.member_names = cast(MemberTable, classdict).member_names
        return result
