import os

import jinja2

from odev.structures import commands
from odev.utils import logging, odoo


_logger = logging.getLogger(__name__)


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
        TEMPLATE_FILE = "vscode_debug_config.jinja"
        self.template = templateEnv.get_template(TEMPLATE_FILE)

    def run(self):
        """
        Validates input, gathers data, calls the generation of the template
        Writes the result to the appropriate file
        """

        repo_path = os.path.realpath(
            self.args.repo
            if os.path.exists(self.args.repo)
            else os.path.join(self.config["odev"].get("paths", "dev"), self.args.repo)
        )
        self.validate(repo_path)
        self.check_database()

        kwargs = {}
        for key, upgrade_directory in self.get_upgrade_repo_paths(self.args).items():
            if self.validate(upgrade_directory):
                kwargs[key] = upgrade_directory

        kwargs.update(version=self.db_version_clean())

        output_dir = os.path.join(repo_path, ".vscode")
        if not os.path.exists(output_dir):
            _logger.info(f"Creating directory {output_dir}")
            os.mkdir(output_dir)
        output_path = os.path.join(output_dir, "launch.json")
        if os.path.exists(output_path):
            _logger.warning(f"File exists: {output_path}")
            if not _logger.confirm("Would you like to overwrite the existing VSCode debug configuration?"):
                return
        with open(output_path, "w") as file:
            file.write(self.render_debug_template(repo_path, **kwargs))

        _logger.info(f"Success. Wrote config to {output_path}")

    def render_debug_template(self, repo_path, **kwargs):
        """
        Converts data (into strings) and generates config from template
        """
        render_kwargs = {
            "database": self.args.database,
            "custom_repo_dir": repo_path,
        }

        custom_modules_to_update = (
            item.name for item in os.scandir(repo_path) if item.is_dir() and item.name[0] != "."
        )
        render_kwargs.update(custom_modules_str=",".join(custom_modules_to_update))

        upgrade_repo_keys_in_kwargs = kwargs.keys() & {
            "upgrade_repo_path",
            "custom_util_repo_path",
        }
        if upgrade_repo_keys_in_kwargs:
            render_kwargs.update(
                upgrade_paths_str=",".join(
                    os.path.join(kwargs[upgrade_repo], "migrations") for upgrade_repo in upgrade_repo_keys_in_kwargs
                )
            )

        repos_path = self.config["odev"].get("paths", "odoo", "/")
        version = kwargs.get("version")
        assert version is not None
        version_path = odoo.repos_version_path(repos_path, version)
        render_kwargs.update(odoo_dir=os.path.join(version_path, "odoo/"))
        render_kwargs.update(venv_python_bin=os.path.join(version_path, "venv/bin/python"))

        return self.template.render(**render_kwargs)
