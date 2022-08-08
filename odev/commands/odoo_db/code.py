import os
import shutil
from typing import Dict

import jinja2

from odev.structures import commands
from odev.utils import logging, odoo


_logger = logging.getLogger(__name__)

LAUNCH_JSON_TEMPLATE_FILE = "vscode_debug_launch.jinja"
TASKS_JSON_TEMPLATE_FILE = "vscode_debug_tasks.jinja"


class VSCodeDebugConfigCommand(commands.LocalDatabaseCommand, commands.OdooUpgradeRepoMixin):
    """
    Generate a VSCode debug config for a database and repository
    """

    name = "code"
    arguments = [
        {
            "name": "repo",
            "help": "Repo name or path",
        },
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        template_dir = os.path.join(os.path.dirname(__file__), "../../templates/debug/")
        templateLoader = jinja2.FileSystemLoader(searchpath=template_dir)
        templateEnv = jinja2.Environment(loader=templateLoader)
        self.filename_to_template = {
            "launch.json": templateEnv.get_template(LAUNCH_JSON_TEMPLATE_FILE),
            "tasks.json": templateEnv.get_template(TASKS_JSON_TEMPLATE_FILE),
        }

    @property
    def repo_path(self):
        repo_path = os.path.realpath(
            self.args.repo
            if os.path.exists(self.args.repo)
            else os.path.join(self.config["odev"].get("paths", "dev"), self.args.repo)
        )
        self.validate(repo_path)
        self.check_database()
        return repo_path

    def run(self):
        render_kwargs = self.get_render_kwargs()

        output_dir = os.path.join(self.repo_path, ".vscode")
        if not os.path.exists(output_dir):
            _logger.info(f"Creating directory {output_dir}")
            os.mkdir(output_dir)

        for vscode_config_filename in self.filename_to_template.keys():
            output_path = os.path.join(output_dir, vscode_config_filename)
            if os.path.exists(output_path):
                _logger.warning(f"File exists: {output_path}")
                if not _logger.confirm(f"Would you like to overwrite the existing VSCode {vscode_config_filename}?"):
                    return

            with open(output_path, "w") as file:
                file.write(self.render_debug_template(vscode_config_filename, **render_kwargs))

        _logger.info(f"Success. Wrote config to {output_path}")

    def get_render_kwargs(self) -> Dict[str, str]:
        """
        Computes & converts data into renderable strings
        """
        render_kwargs = {
            "dbname": self.args.database,
            "custom_repo_dir": self.repo_path,
        }
        upgrade_path_parameters = []
        for upgrade_directory in self.get_upgrade_repo_paths(self.args).values():
            if upgrade_directory and self.validate(upgrade_directory):
                upgrade_path_parameters.append(upgrade_directory)

        if upgrade_path_parameters:
            render_kwargs.update(
                upgrade_paths_str=",".join(
                    os.path.join(upgrade_path, "migrations") for upgrade_path in upgrade_path_parameters
                )
            )

        custom_modules_to_update_or_install = (
            item.name
            for item in os.scandir(self.repo_path)
            if item.is_dir() and item.name[0] != "." and item.name != "util_package"
        )
        render_kwargs.update(custom_modules_str=",".join(custom_modules_to_update_or_install))

        repos_path = self.config["odev"].get("paths", "odoo", "/")
        version = self.db_version_clean()
        assert version is not None
        version_path = odoo.repos_version_path(repos_path, version)
        render_kwargs.update(odoo_dir=os.path.join(version_path, "odoo/"))
        render_kwargs.update(venv_python_bin=os.path.join(version_path, "venv/bin/python"))

        render_kwargs["local_mailcatcher_cmd"] = None
        for cmd in ("mailcatcher", "mailhog"):
            if shutil.which(cmd):
                render_kwargs["local_mailcatcher_cmd"] = cmd
                break

        render_kwargs["empty_dbname"] = f"{self.args.database}_empty"

        return render_kwargs

    def render_debug_template(self, vscode_config_filename: str, **render_kwargs: Dict[str, str]) -> str:
        """
        Renders config from template
        """
        template = self.filename_to_template[vscode_config_filename]
        return template.render(**render_kwargs)
