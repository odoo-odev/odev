'''Downloads a dump from a SaaS or SH database.'''

import gzip
import os
import re
import shutil
from argparse import Namespace
from datetime import datetime

from odev.structures import commands
from odev.utils import logging
from odev.utils.os import mkdir
from odev.utils.curl import curl
from odev.exceptions import CommandAborted


_logger = logging.getLogger(__name__)


re_url = re.compile(r'^https?://')
re_session = re.compile(r'session_id=([^;]+)')
re_location = re.compile(r'Location:\s([^\s\n]+)')
re_redirect = re.compile(r'href=\'([^\']+)')
re_csrf = re.compile(r'name=\'csrf_token\'\svalue=\'([a-z0-9]+)\'')
re_error = re.compile(r'^HTTP/.{3}\s[^23].{2}')
re_database = re.compile(r'^https?://([a-zA-Z0-9_-]+)\.')
re_directory = re.compile(r'(/|\\)$')
re_sh_dump = re.compile(r'href=\'//([a-z0-9]+.odoo.com/_long/paas/build/[0-9]+/dump)[a-z.]+\?token')
re_sh_token = re.compile(r'\?token=([^\']+)')


class DumpCommand(commands.LocalDatabaseCommand):
    '''
    Download a dump of a SaaS or SH database and save it locally.
    You can choose whether to download the filestore or not.
    '''

    name = 'dump'
    database_required = False
    arguments = [
        dict(
            aliases=['url'],
            help='URL to the database to dump, in the form of https://db.odoo.com',
        ),
        dict(
            aliases=['destination'],
            metavar='dest',
            help='Directory to which the dumped file will be saved once downloaded',
        )
    ]

    def __init__(self, args: Namespace):
        super().__init__(args)
        self.url = ('https://' if not re_url.match(args.url) else '') + args.url
        self.destination = args.destination
        if not re_directory.search(self.destination):
            self.destination = self.destination + '/'
        self.database = args.database

    def run(self):
        '''
        Dumps a SaaS or SH database.
        '''

        # ---------------------------------------------------------------------
        # Find out on which platform the database is running (SaaS or SH)
        # ---------------------------------------------------------------------

        _logger.info(f'Logging you in to {self.url} support console')

        support_url = f'{self.url}/_odoo/support'
        support_login_url = f'{support_url}/login'

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
        login = _logger.ask('Login:')
        passwd = _logger.password('Password:')
        reason = _logger.ask('Reason (optional):')

        login_url = support_login_url if platform == 'saas' else re_location.findall(res)[-1]

        res = curl(
            login_url,
            '-X POST',
            f'-d "login={login}&password={passwd}&reason={reason}&csrf_token={csrf}"',
            f'-H "Cookie: session_id={session}"',
            follow_redirects=False,
        )
        if re_error.match(res):
            raise Exception('Error logging you in, check your credentials and try again')

        match = re_session.search(res)
        session = match and match[1]

        if not session:
            raise Exception('Invalid session id, check your credentials and try again')

        if platform == 'sh':
            match = re_redirect.search(res)
            redirect = match and match[1]
            res = curl(f'https://www.odoo.sh{redirect}', f'-H "Cookie: session_id={session}"')
            session = re_session.findall(res)[-1]
            login_url = re_location.findall(res)[-1]
        elif platform == 'saas':
            login_url = support_url

        _logger.success(f'Successfuly logged-in to {login_url}')

        # ---------------------------------------------------------------------
        # Get the link the the dump file and download it
        # ---------------------------------------------------------------------

        database_name = self.database
        if not database_name:
            match = re_database.search(login_url)
            database_name = match and match[1]

        _logger.info(f'About to download dump file for {database_name}')

        ext = 'dump' if platform == 'saas' else 'sql.gz'
        if _logger.confirm('Do you want to include the filestore?'):
            ext = 'zip'

        if not os.path.isdir(self.destination):
            mkdir(self.destination)

        timestamp = datetime.now().strftime('%Y%m%d')
        base_dump_filename = f'{self.destination}{timestamp}_{database_name}.dump'
        destfile = f'{base_dump_filename}.{ext}'

        if os.path.isfile(destfile):
            _logger.warning(
                f'The file {destfile} already exists, '
                f'indicating that you most probably already dumped this database today',
            )
            overwrite = _logger.confirm('Do you wish to overwrite this file?')
            if not overwrite:
                raise CommandAborted()

        dump_url = ''

        if platform == 'sh':
            match = re_sh_token.search(login_url)
            token = match and match[1]
            match = re_sh_dump.search(res)
            matched_url = match and match[1]
            dump_url = f'{matched_url}.{ext}?token={token}'
        elif platform == 'saas':
            dump_url = f'{self.url}/saas_worker/dump.{ext}'

        _logger.info(f'Downloading dump from {dump_url} to {destfile}...')
        _logger.warning('This may take a while, please be patient...')

        res = curl(
            dump_url,
            f'-o "{destfile}"',
            f'-H "Cookie: session_id={session}"',
            include_response_headers=False,
            silent=False,
        )

        if re_error.match(res):
            raise Exception(
                f'Error downloading dump from {dump_url}\n'
                'Maybe the database is too big to be dumped, '
                'in which case please contact the SaaS support team '
                'and ask them for a dump of the database'
            )
        if not os.path.isfile(destfile):
            raise Exception('Error while saving dump file to disk')

        if ext == 'sql.gz':
            _logger.info(f'Extracting `{base_dump_filename}.sql`')
            with gzip.open(destfile, 'rb') as f_in:
                with open(f'{base_dump_filename}.sql', 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)

        _logger.success('Successfuly downloaded dump file')

        return 0
