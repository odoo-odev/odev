import re
from argparse import ArgumentParser, Namespace
from pathlib import Path

from odev.common import args as arg_defs
from odev.common.actions import ACTIONS_MAPPING, IntAction, ListAction

from tests.fixtures import OdevTestCase


class TestArgumentToDict(OdevTestCase):
    def test_string_argument_to_dict(self):
        spec = arg_defs.String(name="label", aliases=["-l"], description="A label", default="x")
        d = spec.to_dict("ignored")
        self.assertEqual(d["name"], "label")
        self.assertEqual(d["action"], "store")
        self.assertEqual(d["default"], "x")
        self.assertIn("-l", d["aliases"])

    def test_integer_argument_to_dict(self):
        spec = arg_defs.Integer(default=3)
        d = spec.to_dict("count")
        self.assertEqual(d["name"], "count")
        self.assertEqual(d["action"], "store_int")

    def test_flag_default_false_uses_store_true(self):
        spec = arg_defs.Flag(default=False)
        d = spec.to_dict("verbose")
        self.assertEqual(d["action"], "store_true")

    def test_flag_default_true_uses_store_false(self):
        spec = arg_defs.Flag(default=True)
        d = spec.to_dict("quiet")
        self.assertEqual(d["action"], "store_false")

    def test_list_argument_to_dict(self):
        spec = arg_defs.List(default=["a"])
        d = spec.to_dict("items")
        self.assertEqual(d["action"], "store_list")

    def test_path_argument_to_dict(self):
        spec = arg_defs.Path()
        d = spec.to_dict("out")
        self.assertEqual(d["action"], "store_path")

    def test_regex_argument_to_dict(self):
        spec = arg_defs.Regex()
        d = spec.to_dict("pattern")
        self.assertEqual(d["action"], "store_regex")

    def test_eval_argument_to_dict(self):
        spec = arg_defs.Eval()
        d = spec.to_dict("literal")
        self.assertEqual(d["action"], "store_eval")


class TestArgparseCustomActions(OdevTestCase):
    def test_store_int_action(self):
        parser = ArgumentParser()
        parser.add_argument("--n", action=ACTIONS_MAPPING["store_int"])
        ns = parser.parse_args(["--n", "42"])
        self.assertEqual(ns.n, 42)

    def test_store_list_action(self):
        parser = ArgumentParser()
        parser.add_argument("--tags", action=ACTIONS_MAPPING["store_list"])
        ns = parser.parse_args(["--tags", "a,b,c"])
        self.assertEqual(ns.tags, ["a", "b", "c"])

    def test_store_path_action(self):
        parser = ArgumentParser()
        parser.add_argument("--p", action=ACTIONS_MAPPING["store_path"])
        ns = parser.parse_args(["--p", str(self.run_path)])
        self.assertIsInstance(ns.p, Path)
        self.assertTrue(ns.p.is_absolute())

    def test_store_regex_action(self):
        parser = ArgumentParser()
        parser.add_argument("--re", action=ACTIONS_MAPPING["store_regex"])
        ns = parser.parse_args(["--re", "^foo$"])
        self.assertIsInstance(ns.re, re.Pattern)
        self.assertTrue(ns.re.match("foo"))

    def test_store_eval_action(self):
        parser = ArgumentParser()
        parser.add_argument("--e", action=ACTIONS_MAPPING["store_eval"])
        ns = parser.parse_args(["--e", "{'k': 1}"])
        self.assertEqual(ns.e, {"k": 1})

    def test_int_action_invalid_value_raises(self):
        action = IntAction(option_strings=("--x",), dest="x")
        with self.assertRaises(ValueError):
            action(None, Namespace(), "not-an-int", "--x")

    def test_list_action_wraps_invalid_transform(self):
        action = ListAction(option_strings=("--x",), dest="x")

        def bad_transform_one(value):
            raise ValueError("nope")

        action._transform_one = bad_transform_one  # type: ignore[method-assign]
        with self.assertRaises(ValueError) as ctx:
            action(None, Namespace(), "a,b", "--x")
        self.assertIn("Invalid value(s) for x", str(ctx.exception))
