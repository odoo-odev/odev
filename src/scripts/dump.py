# -*- coding: utf-8 -*-

import re
import os
from datetime import datetime
from urllib.parse import unquote
import gzip
import shutil

from . import script
from .. import utils

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


class DumpScript(script.Script):

    def run(self, database, options):
        """
        Dumps a SaaS or SH database.
        """

        utils.require('url', options[0])
        utils.require('destination', options[1])

        url = options[0]

        if not re_url.match(url):
            url = 'https://%s' % (url)

        base_url = url
        destination = options[1]

        # ---------------------------------------------------------------------
        # Find out on which platform the database is running (SaaS or SH)
        # ---------------------------------------------------------------------

        utils.log('info', 'Logging you in to %s support console' % (url))

        curl = 'curl -iksL %s/_odoo/support/login' % (url)
        stream = os.popen(curl)
        res = stream.read().strip()

        platform = 'saas'

        if re_error.match(res):
            # Retry for without '/login' as the support page on odoo.sh is not database-dependant
            curl = 'curl -iksL %s/_odoo/support' % (url)
            stream = os.popen(curl)
            res = stream.read().strip()

            if re_error.match(res):
                raise Exception('Error fetching webpage, check the URL and try again')

            platform = 'sh'

        # ---------------------------------------------------------------------
        # Login to the support page
        # ---------------------------------------------------------------------

        match = re_session.findall(res)
        session = match[-1]

        match = re_csrf.findall(res)
        csrf = match[-1]

        login = utils.ask('Login:')
        passwd = utils.password('Password:')
        reason = utils.ask('Reason (optional):')

        if platform == 'saas':
            url = '%s/_odoo/support/login' % (url)
        elif platform == 'sh':
            match = re_location.findall(res)
            url = match[-1]

        curl = 'curl -iks -X POST "%s" -d "login=%s&password=%s&reason=%s&csrf_token=%s" -H "Cookie: session_id=%s"' % (url, login, passwd, reason, csrf, session)

        stream = os.popen(curl)
        res = stream.read().strip()

        if re_error.match(res):
            raise Exception('Error logging you in, check your credentials and try again')

        match = re_session.search(res)
        session = match[1]

        if not session:
            raise Exception('Invalid session id, check your credentials and try again')

        if platform == 'sh':
            match = re_redirect.search(res)
            redirect = match[1]

            curl = 'curl -iksL "https://www.odoo.sh%s" -H "Cookie: session_id=%s"' % (
                redirect, session)
            stream = os.popen(curl)
            res = stream.read().strip()

            match = re_session.findall(res)
            session = match[-1]

            match = re_location.findall(res)
            url = match[-1]
        elif platform == 'saas':
            url = '%s/_odoo/support' % (base_url)

        utils.log('success', 'Successfuly logged-in to %s' % (url))

        # ---------------------------------------------------------------------
        # Get the link the the dump file and download it
        # ---------------------------------------------------------------------

        utils.log('info', 'About to download dump file for %s' % (database))

        ext = 'dump' if platform == 'saas' else 'sql.gz'

        if utils.confirm('Do you want to include the filestore?'):
            ext = 'zip'

        if not os.path.isdir(destination):
            utils.mkdir(destination)

        if not database:
            match = re_database.search(url)
            database = match[1]

        if not re_directory.match(destination):
            destination = '%s/' % (destination)

        timestamp = datetime.now().strftime('%Y%m%d')

        destfile = '%s%s_%s.dump.%s' % (destination, timestamp, database, ext)

        if os.path.isfile(destfile):
            utils.log('warning', 'The file %s already exists, indicating that you most probably already dumped this database today' % (destfile))
            overwrite = utils.confirm('Do you wish to overwrite this file?')

            if not overwrite:
                utils.log('info', 'Action canceled')
                return 0

        if platform == 'sh':
            match = re_sh_token.search(url)
            token = match[1]

            match = re_sh_dump.search(res)
            url = match[1]

            url = '%s.%s?token=%s' % (url, ext, token)
        elif platform == 'saas':
            url = '%s/saas_worker/dump.%s' % (base_url, ext)

        utils.log('info', 'Downloading dump from %s to %s...' % (url, destfile))
        utils.log('warning', 'This may take a while, please be patient...')

        curl = 'curl -kL %s -o %s -H "Cookie: session_id=%s"' % (url, destfile, session)
        stream = os.popen(curl)
        res = stream.read().strip()

        if re_error.match(res):
            raise Exception('Error downloading dump from %s\nMaybe the database is too big to be dumped, in which case please contact the SaaS support team and ask them for a dump of the database' % (url))

        if not os.path.isfile(destfile):
            raise Exception('Error while saving dump file to disk')

        if ext == 'sql.gz':
            with gzip.open(destfile, 'rb') as f_in:
                with open('%s%s_%s.dump.sql' % (destination, timestamp, database), 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)

        utils.log('success', 'Successfuly downloaded dump file')

        return 0
