import pytest

from odev.structures.commands import BaseCommand


def test_merge_arguments():
    class MissingArgNameCommand(BaseCommand):
        arguments = [{"help": "bad argument, no name"}]

    class ParentCommand(BaseCommand):
        arguments = [
            {"name": "pos1"},
            {"name": "pos2", "help": "before override"},
            {"aliases": ["pos3"]},  # with aliases
        ]

    class ChildCommand(ParentCommand):
        arguments = [
            {"name": "pos4"},
            {"dest": "pos5"},  # with dest
            {"name": "pos6"},
        ]

    class OverridingChildCommand(ChildCommand):
        arguments = [
            {"name": "pos5"},
            {"name": "pos7"},
            {"name": "pos8"},
            {"name": "pos2", "help": "after override"},
        ]

    def get_positional_names_ordered(command_cls):
        arguments = command_cls._get_merged_arguments()
        return [arg["name"] for arg in arguments if not arg["name"].startswith("-")]

    def get_argument_by_name(command_cls, arg_name):
        arguments = command_cls._get_merged_arguments()
        for arg in arguments:
            if arg["name"] == arg_name:
                return arg

    with pytest.raises(ValueError) as exc_info:
        MissingArgNameCommand._get_merged_arguments()
    assert "Missing name" in str(exc_info.value), "should raise on missing argument name"

    assert get_argument_by_name(ParentCommand, "pos3"), "should derive argument name from aliases"

    assert get_argument_by_name(ChildCommand, "pos5"), "should derive argument name from dest"

    assert all(
        arg.get("name") and arg.get("aliases") for arg in OverridingChildCommand._get_merged_arguments()
    ), "all arguments should have names and aliases"

    assert (
        get_argument_by_name(OverridingChildCommand, "pos2")["help"]
        != get_argument_by_name(ParentCommand, "pos2")["help"]
    ), "children arguments can override values from inherited ones"

    expected_order = ["pos1", "pos2", "pos3", "pos4", "pos5", "pos6"]
    assert (
        get_positional_names_ordered(ChildCommand) == expected_order
    ), "inherited positional arguments should come before children ones"

    expected_order = ["pos1", "pos3", "pos4", "pos6", "pos5", "pos7", "pos8", "pos2"]
    assert (
        get_positional_names_ordered(OverridingChildCommand) == expected_order
    ), "overridden inherited positional arguments should be popped and moved ~last"
