import datetime
import os
import re
from argparse import Namespace
from pathlib import Path
from typing import Tuple

import lxml.etree as et
import odoolib
from git import Repo

from odev.exceptions.commands import CommandAborted, InvalidArgument
from odev.structures import commands
from odev.utils import logging
from odev.utils.credentials import CredentialsHelper
from odev.utils.os import mkdir


logger = logging.getLogger(__name__)

TS_CONFIG = "timesheets.xml"
TS_SCHEMA = "timesheets.xsd"


class TimesheetCommand(commands.Command):
    """
    Create timesheets.
    """

    ts_config: et.ElementTree
    project: et.Element
    connection: odoolib.Connection
    task: str
    description: str
    time: float

    name = "timesheet"
    aliases = ["ts"]
    arguments = [
        {
            "name": "task",
            "help": "Task for which the timesheet will be created",
            "nargs": "?",
            "default": "",
        },
        {
            "name": "description",
            "help": "Description for the timesheet",
            "nargs": "?",
            "default": "",
        },
        {
            "name": "time",
            "help": "Amount of time for the timesheet",
        },
        {
            "aliases": ["-s", "--shortcut"],
            "dest": "shortcut",
            "action": "store_true",
            "help": "Use a shortcut to task",
        },
    ]

    def __init__(self, args: Namespace):
        super().__init__(args)
        self.task = self.args.task
        self.description = self.args.description
        self.shortcut = self.args.shortcut
        try:
            self.time = float(self.args.time)
        except ValueError:
            raise InvalidArgument("Time must be a float")

        self.ts_config = self._get_ts_config()
        self.project = self._get_project()
        self.connection = self._get_connection()

    def _get_ts_config(self) -> et.ElementTree:
        directory = os.path.join(Path.home(), ".config", "odev")
        file = os.path.join(directory, TS_CONFIG)
        if not os.path.isdir(directory):
            mkdir(directory)
        template_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..",
            "..",
            "templates",
            "timesheet",
        )
        if not os.path.isfile(file):
            # Copy template
            template_filepath = os.path.join(template_dir, TS_CONFIG)
            with open(file, "w") as config_file, open(template_filepath, "r") as template_file:
                config_file.write(template_file.read())
        schema = et.XMLSchema(file=os.path.join(template_dir, TS_SCHEMA))
        parser = et.XMLParser(schema=schema)
        configs = et.parse(file, parser)
        return configs

    def _get_project(self) -> et.Element:
        if not self.shortcut:
            cwd = os.getcwd()
            for project in self.ts_config.findall("projects/project"):
                if "name" in project.attrib and project.attrib["name"] in cwd:
                    logger.info(f'Using project "{project.attrib["name"]}"')
                    return project
            default = self.ts_config.find("default")
            if default is not None and "project" in default.attrib:
                project = self.ts_config.find(f'projects/project[@name="{default.attrib["project"]}"]')
                if project is None:
                    raise InvalidArgument(f'Could not find default project "{default.attrib["project"]}"')
                logger.info(f'Using default project "{project.attrib["name"]}"')
                return project
            raise InvalidArgument("Could not find project")
        else:
            for shortcut in self.ts_config.findall("shortcuts/shortcut"):
                if "name" in shortcut.attrib and shortcut.attrib["name"] == self.task:
                    logger.info(f'Using shortcut "{shortcut.attrib["name"]}"')
                    return shortcut
            raise InvalidArgument("Could not find shortcut")

    def _get_connection(self) -> odoolib.Connection:
        name = self.project.attrib["connection"]
        elem = self.ts_config.find(f'connections/connection[@name="{name}"]')
        if elem is None:
            raise InvalidArgument(f'Could not find connection parameters for "{name}"')
        params = elem.attrib
        with CredentialsHelper() as creds:
            login = creds.get(f"{name}.login", f"Login for {name}:")
            password = creds.secret(f"{name}.apikey", f"API key for {login}:")
            return odoolib.get_connection(
                hostname=params["url"],
                database=params["db"],
                login=login,
                password=password,
                protocol="jsonrpcs",
                port=443,
            )

    def run(self):
        """
        Create a timesheet line.
        """
        if self.shortcut:
            description = self.description or self._get_shortcut_description()
            record_id, mode = self._get_shortcut_data()
            self._timesheet(description, record_id, mode)
        else:
            if not self.task and not self.description:
                self.task, self.description = self._scrap()
            if not self.description:
                self.description = self._get_default_description()
            task_id = self._map_task_to_id()
            description = self._format_description()
            self._timesheet(description, task_id)
        return 0

    def _timesheet(self, description: str, record_id: int, mode: str = "task"):
        model, field = {
            "task": ("project.task", "task_id"),
            "project": ("project.project", "project_id"),
        }[mode]
        # Ask for confirmation
        target_name = self.connection.get_model(model).read([record_id], fields=["name"])[0]["name"]
        if not logger.confirm(f'Timesheet "{description}" on {mode} "{target_name}" (id={record_id})?'):
            raise CommandAborted()

        # Get user and employee id
        response = self.connection.get_model("res.users").search_read(
            domain=[("login", "=", self.connection.login)], fields=["employee_id"], limit=1
        )[0]
        user_id = response["id"]
        employee_id = response["employee_id"][0]

        ts_line_model = self.connection.get_model("account.analytic.line")
        response = ts_line_model.search_read(
            domain=[
                ("user_id", "=", user_id),
                ("name", "=", description),
                ("employee_id", "=", employee_id),
                ("date", "=", datetime.date.today().strftime("%Y-%m-%d")),
                (field, "=", record_id),
            ],
            fields=["unit_amount"],
        )
        if response:  # Update a matching ts line
            ts_line_model.write([response[0]["id"]], {"unit_amount": response[0]["unit_amount"] + self.time})
        else:
            # Get uom for ts
            uom_id = ts_line_model.search_read(
                domain=[("employee_id", "=", employee_id), ("product_uom_id", "!=", False)],
                fields=["product_uom_id"],
                limit=1,
            )[0]["product_uom_id"][0]
            # Create a new ts line
            ts_line_model.create(
                {
                    "user_id": user_id,
                    "name": description,
                    "unit_amount": self.time,
                    "employee_id": employee_id,
                    "product_uom_id": uom_id,
                    field: record_id,
                },
            )

    def _scrap(self) -> Tuple[str, str]:
        repo = Repo(search_parent_directories=True)
        message = repo.commit().message
        logger.info("Scrapping from last commit message...")
        for scrap in (s.attrib for s in self.project.findall("scrap")):
            match = re.search(scrap["pattern"], message)
            if match:
                task = match.group(int(scrap["task"]))
                description = match.group(int(scrap["description"])) if "description" in scrap else ""
                return task, description
        raise InvalidArgument("Could not extract values from commit message")

    def _get_default_description(self) -> str:
        default = self.ts_config.find("default")
        if default is not None and "description" in default.attrib:
            return default.attrib["description"]
        return "/"

    def _get_shortcut_description(self) -> str:
        description = self.project.attrib.get("description")
        if not description:
            description = self._get_default_description()
        return description

    def _map_task_to_id(self) -> int:
        task = self.task.lower()
        mappings = {m.attrib["from"].lower(): m.attrib["to"] for m in self.project.findall("map")}
        if task in mappings:
            return int(mappings[task])
        if task.isdigit():
            return int(task)
        raise InvalidArgument(f'Could not get a task id from "{self.task}"')

    def _format_description(self) -> str:
        subs = {s.attrib["pattern"]: s.attrib["repl"] for s in self.project.findall("sub")}
        for pattern, repl in subs.items():
            if re.search(pattern, self.description):
                return re.sub(pattern, repl, self.description)
        return self.description

    def _get_shortcut_data(self) -> Tuple[int, str]:
        return int(self.project.attrib["id"]), self.project.attrib["mode"]
