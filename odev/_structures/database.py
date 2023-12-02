from odev._utils import logging
from odev.commands.odoo_db import create, remove
from odev.exceptions import CommandAborted
from odev.structures.commands import TemplateCreateDBCommand


_logger = logging.getLogger(__name__)


class DBExistsCommandMixin(TemplateCreateDBCommand):
    """
    Base class to handle database existence check and override
    """

    def __init__(self, args):
        super().__init__(args)

        if self.db_exists():
            _logger.warning(f"Database {self.database} already exists and is an Odoo database")

            if not _logger.confirm("Do you want to overwrite its content?"):
                raise CommandAborted()

            remove.RemoveCommand.run_with(**self.args.__dict__)

        if not self.db_exists_all():
            create.CreateCommand.run_with(**self.args.__dict__, template=None)
