"""Run an Odoo database locally."""

from odev.common import args, progress, string
from odev.common.commands import OdoobinTemplateCommand
from odev.common.logging import logging
from odev.common.version import OdooVersion


logger = logging.getLogger(__name__)


MODULES_OPTIONS: dict[str, tuple[str, str]] = {"install": ("-i", "--init"), "update": ("-u", "--update")}
"""Short and long odoo-bin options taking a comma-separated list of modules, by operation."""


def merge_modules_option(odoo_args: list[str], option: tuple[str, str], modules: list[str]) -> list[str]:
    """Merge modules into an odoo-bin option, keeping the modules already passed to it by the user.

    odoo-bin only keeps the last occurrence of an option, so all values are gathered into a single one.

    :param odoo_args: Arguments to pass to odoo-bin.
    :param option: Short and long names of the option, e.g. `("-i", "--init")`.
    :param modules: Names of the modules to add to the option.
    :return: The arguments with a single occurrence of the option holding all modules.
    """
    short, long = option
    values: list[str] = []
    remaining: list[str] = []
    iterator = iter(odoo_args)

    for arg in iterator:
        if arg in option:
            values.extend(next(iterator, "").split(","))
        elif arg.startswith(f"{long}="):
            values.extend(arg.split("=", 1)[1].split(","))
        elif arg.startswith(short) and not arg.startswith("--"):
            values.extend(arg[len(short) :].split(","))
        else:
            remaining.append(arg)

    merged = list(dict.fromkeys(module for module in [*values, *modules] if module))
    return [*remaining, short, ",".join(merged)] if merged else remaining


class RunCommand(OdoobinTemplateCommand):
    """Run the odoo-bin process for the selected database locally.

    The process is run in a python virtual environment depending on the database's odoo version (as defined
    by the installed `base` module). The command takes care of installing and updating python requirements within
    the virtual environment and fetching the latest sources in the odoo standard repositories, cloning them
    if necessary. All odoo-bin arguments are passed to the odoo-bin process.
    """

    _name = "run"

    from_template = args.String(
        description="""Name of an existing PostgreSQL database to copy before running.
        If passed without a value, search for a template database with the same name as the new database.
        """
    )
    install_all = args.Flag(
        aliases=["-I", "--install-all"],
        description="""Install all modules found in the repository linked to the database, or in the current
        directory if none is linked, including modules in subdirectories and git submodules.
        Merged with the modules passed to odoo-bin's `-i` option, if any.
        """,
    )
    upgrade_all = args.Flag(
        aliases=["-U", "--upgrade-all"],
        description="""Update all modules found in the repository linked to the database, or in the current
        directory if none is linked, including modules in subdirectories and git submodules.
        Merged with the modules passed to odoo-bin's `-u` option, if any.
        """,
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        if self.args.version:
            version = str(OdooVersion(self.args.version))

            if not self.args.worktree:
                self.args.worktree = version
            else:
                logger.warning("Passing both --version and --worktree is untested and may lead to unexpected results")

            if not self.args.venv:
                self.args.venv = version
            else:
                logger.warning("Passing both --version and --venv is untested and may lead to unexpected results")

        if (self.args.enterprise and self._database.edition == "community") or (
            not self.args.enterprise and self._database.edition == "enterprise"
        ):
            logger.warning(
                f"Forcing {'enterprise' if self.args.enterprise else 'community'} edition "
                f"for database {self._database.name!r} which is set to {self._database.edition!r}"
            )

        self._set_odoobin_process(
            force=any([self.args.version, self.args.venv, self.args.worktree, self.args.enterprise])
        )

    @property
    def _database_exists_required(self) -> bool:
        """Return True if a database has to exist for the command to work."""
        return not bool(self.from_template)

    def run(self):
        """Run the odoo-bin process for the selected database locally."""
        if self._template:
            if not self._template.exists:
                raise self.error(f"Template database {self._template.name!r} does not exist")

            if self._database.exists:
                with progress.spinner(f"Reset database {self._database.name!r} from template {self._template.name!r}"):
                    self._database.drop()

            self.odev.run_command("create", "--from-template", self._template.name, self._database.name)

        if not self.odoobin:
            raise self.error(f"Could not spawn process for database {self._database.name!r}")

        if self.odoobin.is_running:
            raise self.error(f"Database {self._database.name!r} is already running")

        process = self.odoobin.run(args=self._odoo_args_with_modules(), stream_filter=self.odoobin_progress)

        if process and process.returncode:
            raise self.error("Odoo process failed")

    def _odoo_args_with_modules(self) -> list[str]:
        """Add the modules of the additional addons paths to odoo-bin's arguments, if requested."""
        odoo_args = list(self.args.odoo_args)
        flags = {"install": self.args.install_all, "update": self.args.upgrade_all}
        operations = [operation for operation, enabled in flags.items() if enabled]

        if not operations or self.odoobin is None:
            return odoo_args

        modules = self.odoobin.list_addons(self.odoobin.additional_addons_paths)

        if not modules:
            raise self.error(
                f"No module found to {string.join_and(operations)} for database {self._database.name!r}, "
                "run the command from within a repository containing Odoo modules"
            )

        for operation in operations:
            logger.info(f"Modules to {operation}:\n{string.join_bullet(modules)}")
            odoo_args = merge_modules_option(odoo_args, MODULES_OPTIONS[operation], modules)

        return odoo_args
