from odev.common import args

from tests.fixtures import OdevTestCase


class TestCommonArguments(OdevTestCase):

    def test_argument_string(self):
        arg_string = args.String(name="str", help="String argument")
        self.assertDictEqual(
            arg_string.to_dict("str"),
            {
                "name": "str",
                "help": "String argument",
                "action": "store",
            },
            "should convert the string argument to a valid mapping, optional keys should not be set",
        )

        arg_string = args.String(name="str", help="String argument", aliases=["s"], default="default")
        self.assertDictEqual(
            arg_string.to_dict("str"),
            {
                "name": "str",
                "help": "String argument",
                "action": "store",
                "aliases": ["s"],
                "default": "default",
            },
            "should convert the string argument to a valid mapping, optional keys should be set",
        )

    def test_argument_flag(self):
        arg_flag = args.Flag(name="flag", help="Flag argument")
        self.assertDictEqual(
            arg_flag.to_dict("flag"),
            {
                "name": "flag",
                "help": "Flag argument",
                "action": "store_true",
            },
            "should convert the flag argument to a valid mapping, action should be set to store_true "
            "when default is not set",
        )

        arg_flag = args.Flag(name="flag", help="Flag argument", default=False)
        self.assertDictEqual(
            arg_flag.to_dict("flag"),
            {
                "name": "flag",
                "help": "Flag argument",
                "action": "store_true",
            },
            "should convert the flag argument to a valid mapping, action should be set to store_true "
            "when default is set to False",
        )

        arg_flag = args.Flag(name="flag", help="Flag argument", default=True)
        self.assertDictEqual(
            arg_flag.to_dict("flag"),
            {
                "name": "flag",
                "help": "Flag argument",
                "action": "store_false",
            },
            "should convert the flag argument to a valid mapping, action should be set to store_false "
            "when default is set to True",
        )
