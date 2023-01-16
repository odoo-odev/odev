import os
import subprocess
from argparse import Namespace
from typing import List

from odev.commands.odoo_bin import run
from odev.utils import logging


_logger = logging.getLogger(__name__)

PATH = os.path.dirname(os.path.realpath(__file__))
TOOLS_DIRECTORY = PATH + "/../shell_scripts"


class ShellCommand(run.RunCommand):
    """
    Open the Odoo shell for a local database.
    """

    name = "shell"
    odoobin_subcommand = "shell"

    shell_commands: List[str] = []

    arguments = [
        {
            "dest": "file",
            "aliases": ["--script"],
            "help": "Script to run in odoo-bin shell",
        },
    ]

    def run_odoo(self, **kwargs) -> subprocess.CompletedProcess:
        if not self.shell_commands:
            return super().run_odoo(**kwargs)
        command_input = "{ " + " ; ".join(self.shell_commands) + " ; } | "

        kwargs["additional_args"].append("--log-level=critical")
        return super().run_odoo(command_input=command_input, print_cmdline=False, **kwargs)

    def __init__(self, args: Namespace):
        filename = args.file
        if filename:
            # load script
            self.shell_commands = ["cat " + filename]

        super().__init__(args)


class ShortestPathCommand(ShellCommand):
    """
    Show the n shortests paths from the model A to model B on database.
    The module(s) that define model A and B should be installed on the database.
    Ex: odev shortest_path myDB mrp.production sale.order
        self.message_partner_ids.sale_order_ids
        self.lot_producing_id.sale_order_ids
        self.procurement_group_id.sale_id
        self.picking_ids.sale_id
        self.lot_producing_id.purchase_order_ids.auto_sale_order_id
    """

    name = "shortest_path"

    arguments = [
        {
            "dest": "file",
            "aliases": ["--script"],
            "default": TOOLS_DIRECTORY + "/shortest_path.py",
        },
        {
            "aliases": ["model_a"],
            "nargs": 1,  # type: ignore
            "help": "The model to start from",
        },
        {
            "aliases": ["model_b"],
            "nargs": 1,  # type: ignore
            "help": "The goal model to end at",
        },
        {
            "dest": "nb_paths",
            "aliases": ["--nb-paths"],
            "default": 10,  # type: ignore
            "help": "Number of paths to return",
        },
        # move positional args from OdooBinMixin after "source"
        {"name": "addons"},
        {"name": "args"},
    ]

    def __init__(self, args: Namespace):
        model_a = args.model_a[0]
        model_b = args.model_b[0]
        nb_paths = args.nb_paths
        delattr(args, "model_a")
        delattr(args, "model_b")
        delattr(args, "nb_paths")

        super().__init__(args)

        _logger.info(f"{nb_paths} shortest paths from {model_a} to {model_b} on database {args.database}:\n")
        self.shell_commands.append(
            f"echo \"shortest_path(self.env, '{model_a}', '{model_b}',n={nb_paths})\"",
        )
