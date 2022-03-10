import csv
import json
import os
import re
import shlex
import shutil
import subprocess
import time
from base64 import b64encode
from datetime import datetime
from typing import (
    Any,
    Dict,
    List,
    Mapping,
    Optional,
    Set,
    Tuple,
    Union,
)

import black
import tldextract
from git import GitCommandError, Repo
from pre_commit.constants import CONFIG_FILE as PRE_COMMIT_CONFIG_FILE

from odev.commands.github import clone
from odev.commands.odoo_db import create, init, remove
from odev.commands.odoo_db.create import _logger as create_command_logger
from odev.exceptions import InvalidFileArgument
from odev.exceptions.commands import InvalidArgument
from odev.exceptions.git import HeadRefMismatch
from odev.structures import commands
from odev.utils import logging, odoo
from odev.utils.credentials import CredentialsHelper
from odev.utils.github import is_git_repo
from odev.utils.odoo import get_manifest, is_really_module, list_submodule_addons
from odev.utils.rpc import OdooRPC
from odev.utils.shconnector import get_sh_connector


_logger = logging.getLogger(__name__)

re_url = re.compile(r"^https?://.+?\.odoo.com")
re_odoo_ps_repo = re.compile(r"^odoo-ps$")
re_test_results = re.compile(r"odoo\.tests\.runner: ((\d+) failed, (\d+) error\(s\) of (\d+) tests)")
re_test_results_fallback = re.compile(r": Ran (\d+) tests in \d+\.\d+s")
re_test_results_fallback_errors = re.compile(r": Module .+?: (\d+) failures, (\d+) errors")
re_build_errors = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} \d+ (?:ERROR|WARNING) .+?)\n", re.MULTILINE)

CSV_COLUMN_URL = "Url"


class OdooSHMonitorCommand(commands.OdooComCliMixin, commands.BaseCommand):
    """
    Parses a CSV file containing database information (from `odoo.com` SH projects list),
    run tests on a the production database' source code and report results to the PS Tools
    database for monitoring.
    """

    name = "sh-monitor"
    aliases = ["monitor", "mon"]
    database_required = False

    arguments = [
        {
            "name": "file",
            "metavar": "file",
            "nargs": "?",
            "help": "Path to a CSV file containing the list of Odoo SH projects to monitor",
        },
        {
            "name": "url",
            "metavar": "url",
            "nargs": "?",
            "help": "URL of a single Odoo SH database to monitor",
        },
        {
            "name": "--assigned",
            "dest": "filter_assigned",
            "action": "store_true",
            "help": "Only check databases if already assigned in PS-Tools SH Monitoring",
        },
        {
            "name": "--unassigned",
            "dest": "filter_unassigned",
            "action": "store_true",
            "help": "Only check databases if *not* already assigned in PS-Tools SH Monitoring",
        },
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if re_url.match(self.args.file):
            self.args.file, self.args.url = self.args.url, self.args.file

        if self.args.file and self.args.url:
            raise InvalidArgument("Cannot use both arguments `file` and `url` at the same time")

        if not self.args.file and not self.args.url:
            raise InvalidArgument("One argument of `file` or `url` is required")

        self.extractor = tldextract.TLDExtract(cache_dir=False)
        self.file: Optional[str] = self.args.file and os.path.normpath(os.path.expanduser(self.args.file))
        self.pulled_odoo_versions: Set[str] = set()

        self.ps_tools_user: Optional[str] = None
        self.ps_tools_api_key: Optional[str] = None
        self.ps_tools_url: Optional[str] = None
        self.ps_tools_database: Optional[str] = None
        self._init_ps_tools()

    def _init_ps_tools(self):
        self.ps_tools_url = self.config["odev"].get("rpc", "ps_tools_url")
        self.ps_tools_database = self.config["odev"].get("rpc", "ps_tools_database")

        if not self.ps_tools_url:
            self.ps_tools_url = _logger.ask(
                "Please enter the URL to the PS-Tools database to use:",
                "ps-tools.odoo.com",
            )
            self.config["odev"].set("rpc", "ps_tools_url", self.ps_tools_url)

        if not self.ps_tools_database:
            self.ps_tools_database = _logger.ask(
                "Please enter the PS-Tools database to use:",
                "odoo-ps-psbe-ps-tools-main-1849314",
            )
            self.config["odev"].set("rpc", "ps_tools_database", self.ps_tools_database)

        with CredentialsHelper() as credentials:
            self.ps_tools_user = credentials.get(
                "pstools.user",
                "PS-Tools API User:",
                self.ps_tools_user,
            )
            self.ps_tools_api_key = credentials.secret(
                "pstools.api",
                "PS-Tools API Key:",
                self.ps_tools_api_key,
            )

    def _cloc_module(self, path: str, name: str, version: str) -> int:
        # Call `odoo-bin cloc` on the current module, one at a time
        # This is faster than calling `odev cloc` once for all modules combined

        repos_path = self.config["odev"].get("paths", "odoo")
        version_path = odoo.repos_version_path(repos_path, version)
        python_exec = os.path.join(version_path, "venv/bin/python")
        odoobin = os.path.join(version_path, "odoo/odoo-bin")
        command = shlex.join(
            [
                python_exec,
                odoobin,
                "cloc",
                *("-p", os.path.join(path, name)),
            ]
        )

        cloc_result = subprocess.getoutput(command)
        loc = re.findall(rf"{name}(?:\s|\d)+\s+(\d+)", cloc_result)
        return loc[0] if loc else 0

    def _clone_repository(self) -> Tuple[bool, Optional[str]]:
        try:
            clone_command = clone.CloneCommand(args=self.args)
            repo = clone_command.select_repo("sh", silent=True)

            if not repo:
                return False, f"No repository found for {self.args.url}"

            if not re_odoo_ps_repo.match(repo["organization"]):
                return False, f"{repo['repo']} is not part of the odoo-ps organization"

            clone_command.clone(repo)

        except GitCommandError:
            return False, f"Cannot clone repository {self.globals_context.get('repo_git_path', 'unknown')}"

        return True, self.globals_context.get("repo_git_path")

    def _pull_odoo_update(self, version: str):
        if version not in self.pulled_odoo_versions:
            self.pulled_odoo_versions.add(version)
            repos_path = self.config["odev"].get("paths", "odoo")
            odoo.prepare_odoobin(repos_path, version, skip_prompt=True)
            odoo.prepare_requirements(repos_path, version)

    def _rpc_write(self, vals: Dict[str, Any]):
        assert self.ps_tools_url is not None
        assert self.ps_tools_database is not None

        with OdooRPC(
            url=self.ps_tools_url,
            database=self.ps_tools_database,
            username=self.ps_tools_user,
            password=self.ps_tools_api_key,
        ) as connection:
            sh_monitor_model = connection.get_model("sh_projects")
            sh_monitor_record: List[Mapping[str, Any]] = sh_monitor_model.search_read(
                domain=[("url", "=like", f"{self.args.url}%")],
                fields=["id"],
                limit=1,
            )

            sh_monitor_record_id: int = (
                sh_monitor_record[0]["id"] if sh_monitor_record else sh_monitor_model.create({"url": self.args.url})
            )

            sh_monitor_model.write([sh_monitor_record_id], vals)

    def _rpc_read(self, fields: List[str]) -> Mapping[str, Any]:
        assert self.ps_tools_url is not None
        assert self.ps_tools_database is not None
        fields = fields or ["id"]

        with OdooRPC(
            url=self.ps_tools_url,
            database=self.ps_tools_database,
            username=self.ps_tools_user,
            password=self.ps_tools_api_key,
        ) as connection:
            sh_monitor_model = connection.get_model("sh_projects")
            sh_monitor_record: List[Mapping[str, Any]] = sh_monitor_model.search_read(
                domain=[("url", "=like", f"{self.args.url}%")],
                fields=fields,
                limit=1,
            )

            return sh_monitor_record[0] if sh_monitor_record else {}

    def _handle_url(self, url: str):  # noqa: C901 - Complexity
        self.args.url = url

        _logger.info(f"Starting Odoo SH monitoring for {url}")

        # -------------------------------------------------------------
        # Git repository
        # -------------------------------------------------------------

        is_cloned, git_repo_path = self._clone_repository()

        if not is_cloned or git_repo_path is None or not is_git_repo(git_repo_path):
            _logger.warning(f"{git_repo_path or 'Not a valid git repository'}, skipping")
            return

        git_repo_full_name = "/".join(git_repo_path.split("/")[~1:])
        git_repo_name = git_repo_full_name.split("/")[~0]

        # -------------------------------------------------------------
        # Odoo SH project information
        # -------------------------------------------------------------

        sh_connector = get_sh_connector(repo_name=git_repo_name).impersonate()
        project_info = sh_connector.project_info()
        assert project_info is not None

        # -------------------------------------------------------------
        # Create project on https://ps-tools.odoo.com/
        # -------------------------------------------------------------

        self._rpc_write(
            {
                "name": project_info["name"],
                "version": project_info["odoo_branch"],
                "sh_info": json.dumps(project_info, sort_keys=True, indent=4),
                "status": "testing",
            }
        )

        # -------------------------------------------------------------
        # Check Assignations
        # -------------------------------------------------------------~

        is_assigned = self._rpc_read(["project_owner_id"]).get("project_owner_id")

        if self.args.filter_assigned and not is_assigned:
            _logger.warning("Project is not assigned, skipping")
            return

        if self.args.filter_unassigned and is_assigned:
            _logger.warning("Project is assigned, skipping")
            return

        # -------------------------------------------------------------
        # Git Repository
        # -------------------------------------------------------------

        prod_branch = sh_connector.get_prod()[0]["name"]
        git_repo = Repo(git_repo_path)
        git_repo.git.checkout(prod_branch)

        # -------------------------------------------------------------
        # Pull Odoo updates
        # -------------------------------------------------------------

        self._pull_odoo_update(project_info["odoo_branch"])

        # -------------------------------------------------------------
        # Odoo modules
        # -------------------------------------------------------------

        def get_module_info(module: str) -> Dict[str, Union[str, int]]:
            return {
                "name": module,
                "manifest": black.format_str(
                    str(get_manifest(git_repo_path, module)),
                    mode=black.FileMode(line_length=120),
                ),
                "cloc": self._cloc_module(git_repo_path, module, project_info["odoo_branch"]),
            }

        odoo_modules: List[Dict[str, Union[str, int]]] = [
            get_module_info(module) for module in os.listdir(git_repo_path) if is_really_module(git_repo_path, module)
        ]

        for submodule_addon_path in list_submodule_addons([git_repo_path]):
            odoo_modules += [
                get_module_info(module)
                for module in os.listdir(submodule_addon_path)
                if is_really_module(submodule_addon_path, module)
            ]

        if not odoo_modules:
            _logger.warning(f"No custom module found in {git_repo_path}, skipping")
            return

        odoo_modules = sorted(
            {i["name"]: i for i in reversed(odoo_modules)}.values(),
            key=lambda m: m["name"],
        )

        # -------------------------------------------------------------
        # Pre-commit
        # -------------------------------------------------------------
        # Run pre-commit on modules and run `odoo-bin cloc` again

        pre_commit_organization = "odoo-ps"
        pre_commit_repo_name = f"{pre_commit_organization}/psbe-ps-tech-tools"
        pre_commit_branch = f"{project_info['odoo_branch']}-pre-commit-config"
        pre_commit_repo_path = os.path.join(self.config["odev"].get("paths", "dev"), pre_commit_repo_name)

        try:
            if not is_git_repo(pre_commit_repo_path):
                clone.CloneCommand(args=self.args).clone(
                    {
                        "repo": pre_commit_repo_name,
                        "organization": pre_commit_organization,
                        "branch": pre_commit_branch,
                    }
                )

            pre_commit_repo = Repo(pre_commit_repo_path)
            pre_commit_repo.git.checkout(pre_commit_branch)
            pre_commit_repo.git.pull()
        except GitCommandError:
            _logger.warning(f"No pre-commit configuration found for Odoo version {project_info['odoo_branch']}")
        else:
            for file in filter(lambda f: os.path.isfile(f), os.listdir(pre_commit_repo_path)):
                shutil.copy(os.path.join(pre_commit_repo_path, file), git_repo_path)

            _logger.info(f"Running pre-commit in {git_repo_path}")
            pre_commit_config = os.path.join(git_repo_path, PRE_COMMIT_CONFIG_FILE)

            for hook in ["black", "prettier", "isort"]:
                subprocess.getoutput(
                    f"cd {git_repo_path} && pre-commit run --all-files --config {pre_commit_config} {hook}",
                )

        for module in odoo_modules:
            module["cloc_pre_commit"] = self._cloc_module(
                git_repo_path,
                module["name"],  # type: ignore
                project_info["odoo_branch"],
            )

        # Cleanup pre-commit changes
        git_repo.git.clean("-df")
        git_repo.git.checkout("--", ".")

        # Checkout again if we are testing psbe-ps-tech-tools (which should never happen)
        if pre_commit_repo_path == git_repo_path:
            git_repo.git.checkout(prod_branch)

        # -------------------------------------------------------------
        # Update project with modules on https://ps-tools.odoo.com/
        # -------------------------------------------------------------

        self._rpc_write({"modules_ids": [(5, 0, 0), *[(0, 0, module) for module in odoo_modules]]})

        # -------------------------------------------------------------
        # Create local database
        # -------------------------------------------------------------

        self.args.template = False
        self.database = self.args.database = f"odev_{self.name}_{project_info['id']}_{time.monotonic_ns()}".replace(
            "-", "_"
        )

        create_command_logger.setLevel("WARNING")
        create.CreateCommand.run_with(**self.args.__dict__)

        # -------------------------------------------------------------
        # Run tests on database
        # -------------------------------------------------------------

        self.args.version = project_info.get("odoo_branch")
        self.args.pull = False
        self.args.sh_test = True
        self.args.addons = odoo.list_submodule_addons([git_repo_path])
        self.args.save = False
        self.args.from_template = False
        self.args.tags = []
        self.args.args = [
            *("-i", ",".join([module["name"] for module in odoo_modules])),  # type: ignore
            "--test-enable",
        ]

        _logger.info(
            f"Running tests for Odoo version {project_info['odoo_branch']} "
            f"on {self.database} using branch '{prod_branch}' at {git_repo_full_name} "
            f"with {len(odoo_modules)} custom modules:\n"
            + "\n".join([f"{' ' * 5}- {m['name']} ({m['cloc']}/{m['cloc_pre_commit']} lines)" for m in odoo_modules])
        )
        _logger.warning("This might take some time, please be patient...")
        init_command = init.InitCommand
        init_command.capture_output = True
        init_start_time = time.time()
        init_command.run_with(**self.args.__dict__)
        init_exec_time = time.time() - init_start_time
        init_result = self.globals_context.get("init_result", "")

        # -------------------------------------------------------------
        # Fetch build results
        # -------------------------------------------------------------

        build_errors_results: List[str] = re_build_errors.findall(init_result)
        warnings_count = len(list(filter(lambda l: " WARNING " in l, build_errors_results)))
        errors_count = len(build_errors_results) - warnings_count
        build_errors = "\n".join(build_errors_results)

        if errors_count:
            build_status = "red"
            log_method = _logger.error
        elif warnings_count:
            build_status = "orange"
            log_method = _logger.warning
        else:
            build_status = "green"
            log_method = _logger.success

        log_method(f"Build completed: {warnings_count} warnings, {errors_count} errors")

        # -------------------------------------------------------------
        # Fetch test results
        # -------------------------------------------------------------

        tests_results = re_test_results.findall(init_result)

        if not tests_results:
            tests_count = sum(int(x) for x in re_test_results_fallback.findall(init_result))

            if not tests_count:
                _logger.warning("Cannot extract test results from odoo logs, assuming no tests")

            tests_results_zipped = list(zip(*re_test_results_fallback_errors.findall(init_result) or [("0", "0")]))
            tests_results.append(
                [
                    "",
                    sum(int(x) for x in tests_results_zipped[0]),
                    sum(int(x) for x in tests_results_zipped[1]),
                    tests_count,
                ]
            )

        _, failed_tests_count, error_tests_count, all_tests_count = tests_results[0]
        log_method = _logger.error if int(failed_tests_count) or int(error_tests_count) else _logger.success

        log_method(
            f"Tests completed: {failed_tests_count} failed, {error_tests_count} error(s) on {all_tests_count} tests "
            f"in {time.strftime('%H:%M:%S', time.gmtime(init_exec_time))} seconds"
        )

        # -------------------------------------------------------------
        # Save results to https://ps-tools.odoo.com/
        # -------------------------------------------------------------

        self._rpc_write(
            {
                "build_run_time": init_exec_time / 3600,  # Seconds -> Hours
                "test_failed": int(failed_tests_count),
                "test_error": int(error_tests_count),
                "tests_count": int(all_tests_count),
                "build_errors": build_errors,
                "status": build_status,
                "odoo_log": b64encode(init_result.encode()).decode(),
                "odoo_log_filename": (
                    f"{datetime.today().strftime('%Y%m%d')}-"
                    f"{project_info['odoo_branch']}-"
                    f"{project_info['name']}-"
                    f"{prod_branch}.log"
                ),
            }
        )

        # -------------------------------------------------------------
        # Cleanup
        # -------------------------------------------------------------

        remove.RemoveCommand.run_with(**self.args.__dict__)

    def run(self):
        if self.file:
            with open(self.file, newline="") as file:
                reader = csv.DictReader(file, delimiter=",")

                if reader.fieldnames is None:
                    raise InvalidFileArgument(f"Cannot extract columns from {self.file}, is the file empty?", self.file)

                if CSV_COLUMN_URL not in reader.fieldnames:
                    raise InvalidFileArgument(f"Missing column '{CSV_COLUMN_URL}' in {self.file}", self.file)

                for row in reader:
                    self.args.assume_yes = True
                    self._handle_url(row[CSV_COLUMN_URL])
                    print()  # Empty newline to visually differentiate runs
        else:
            self._handle_url(self.args.url)
