# -*- coding: utf-8 -*-

import re
import os
from argparse import ArgumentParser, Namespace
from datetime import datetime
import gzip
import shutil

from .. import utils
from ..cli import CliCommand
from ..utils import curl


re_url = re.compile(r'^https?://')
re_session = re.compile(r'session_id=([^;]+)')
re_location = re.compile(r'Location:\s([^\s\n]+)')
re_redirect = re.compile(r'href="([^"]+)')
re_csrf = re.compile(r'name=\"csrf_token\"\svalue=\"([a-z0-9]+)\"')
re_error = re.compile(r'^HTTP/.{3}\s[^23].{2}')
re_database = re.compile(r'^https?://([a-zA-Z0-9_-]+)\.')
re_directory = re.compile(r'(/|\\)$')
re_sh_dump = re.compile(r'href="//([a-z0-9]+.odoo.com/_long/paas/build/[0-9]+/dump)[a-z.]+\?token')
re_sh_token = re.compile(r'\?token=([^"]+)')


class DumpScript(CliCommand):
    command = "dump"
    help = """
Downloads a dump of a SaaS or SH database and saves it to your computer.
Lets you choose whether to download the filestore or not.
"""

    @classmethod
    def prepare_arguments(cls, parser: ArgumentParser) -> None:
        super().prepare_arguments(parser)
        parser.add_argument(
            "url",
            help="URL to the database to dump, in the form of https://db.odoo.com. "
            "The protocol part (http(s)://) can be omitted.",
        )
        parser.add_argument(
            "destination",
            metavar="DEST",
            help="Directory to which the dumped file will be saved once downloaded.",
        )
        parser.add_argument(
            "database",
            nargs='?',
            help="Name of the database used in the downloaded dump filename. "
                 "Doesn't have to match an actual database.",
        )

    def __init__(self, args: Namespace):
        super().__init__(args)
        self.url = ("https://" if not re_url.match(args.url) else "") + args.url
        self.destination = args.destination
        if not re_directory.match(self.destination):
            self.destination = self.destination + "/"
        self.database = args.database

    def run(self):
        """
        Dumps a SaaS or SH database.
        """

        # ---------------------------------------------------------------------
        # Find out on which platform the database is running (SaaS or SH)
        # ---------------------------------------------------------------------

        utils.log('info', f'Logging you in to {self.url} support console')

        support_url = f"{self.url}/_odoo/support"
        support_login_url = f"{support_url}/login"

        res = curl(support_login_url)
        platform = 'saas'
        if re_error.match(res):
            # Retry for without '/login' as the support page on odoo.sh is not database-dependant
            res = curl(support_url)
            if re_error.match(res):
                raise Exception('Error fetching webpage, check the URL and try again')
            platform = 'sh'

        assert platform in ('saas', 'sh')

        # ---------------------------------------------------------------------
        # Login to the support page
        # ---------------------------------------------------------------------

        session = re_session.findall(res)[-1]
        csrf = re_csrf.findall(res)[-1]
        login = utils.ask('Login:')
        passwd = utils.password('Password:')
        reason = utils.ask('Reason (optional):')

        if platform == 'saas':
            login_url = support_login_url
        elif platform == 'sh':
            login_url = re_location.findall(res)[-1]

        res = curl(
            login_url,
            "-X POST",
            f'-d "login={login}&password={passwd}&reason={reason}&csrf_token={csrf}"',
            f'-H "Cookie: session_id={session}"',
            follow_redirects=False,
        )
        if re_error.match(res):
            raise Exception('Error logging you in, check your credentials and try again')

        session = re_session.search(res)[1]
        if not session:
            raise Exception('Invalid session id, check your credentials and try again')

        if platform == 'sh':
            redirect = re_redirect.search(res)[1]
            res = curl(f"https://www.odoo.sh{redirect}", f'-H "Cookie: session_id={session}"')
            session = re_session.findall(res)[-1]
            login_url = re_location.findall(res)[-1]
        elif platform == 'saas':
            login_url = support_url

        utils.log('success', f'Successfuly logged-in to {login_url}')

        # ---------------------------------------------------------------------
        # Get the link the the dump file and download it
        # ---------------------------------------------------------------------

        database_name = self.database
        if not database_name:
            database_name = re_database.search(login_url)[1]

        utils.log('info', f'About to download dump file for {database_name}')

        ext = 'dump' if platform == 'saas' else 'sql.gz'
        if utils.confirm('Do you want to include the filestore?'):
            ext = 'zip'

        if not os.path.isdir(self.destination):
            utils.mkdir(self.destination)
        if not re_directory.match(self.destination):
            self.destination += "/"

        timestamp = datetime.now().strftime('%Y%m%d')
        base_dump_filename = f'{self.destination}{timestamp}_{database_name}.dump'
        destfile = f'{base_dump_filename}.{ext}'

        if os.path.isfile(destfile):
            utils.log(
                "warning",
                f"The file {destfile} already exists, "
                f"indicating that you most probably already dumped this database today",
            )
            overwrite = utils.confirm("Do you wish to overwrite this file?")
            if not overwrite:
                utils.log('info', 'Action canceled')
                return 0

        if platform == 'sh':
            token = re_sh_token.search(login_url)[1]
            matched_url = re_sh_dump.search(login_url)
            dump_url = f'{matched_url}.{ext}?token={token}'
        elif platform == 'saas':
            dump_url = f'{self.url}/saas_worker/dump.{ext}'

        utils.log('info', f'Downloading dump from {dump_url} to {destfile}...')
        utils.log('warning', 'This may take a while, please be patient...')

        res = curl(
            dump_url,
            f'-o "{destfile}"',
            f'-H "Cookie: session_id={session}"',
            with_headers=False,
            silent=False,
        )

        if re_error.match(res):
            raise Exception(
                f"Error downloading dump from {dump_url}\n"
                "Maybe the database is too big to be dumped, "
                "in which case please contact the SaaS support team "
                "and ask them for a dump of the database"
            )
        if not os.path.isfile(destfile):
            raise Exception('Error while saving dump file to disk')

        if ext == 'sql.gz':
            with gzip.open(destfile, 'rb') as f_in:
                with open(f"{base_dump_filename}.sql", "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)

        utils.log('success', 'Successfuly downloaded dump file')

        return 0
