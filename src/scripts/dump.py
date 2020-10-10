# -*- coding: utf-8 -*-

import re
import os
from datetime import datetime

from . import script
from .. import utils

re_url = re.compile(r'^https?://')
re_session = re.compile(r'session_id=([^;]+)')
re_csrf = re.compile(r'name=\"csrf_token\"\svalue=\"([a-z0-9]+)\"')
re_error = re.compile(r'^HTTP/.{3}\s[^23].{2}')
re_database = re.compile(r'^https?://([a-zA-Z0-9_-]+)\.')
re_directory = re.compile(r'(/|\\)$')


class DumpScript(script.Script):

    def run(self, database, options):
        """
        Dumps a SaaS database.
        """

        utils.require('url', options[0])
        utils.require('destination', options[1])

        url = options[0]

        if not re_url.match(url):
            url = 'https://%s' % (url)

        destination = options[1]

        utils.log('info', 'Logging you in to %s support console' % (url))

        curl = 'curl -iksL %s/_odoo/support/login' % (url)
        stream = os.popen(curl)
        res = stream.read().strip()

        if re_error.match(res):
            raise Exception('Error fetching webpage, check the URL and try again')

        match = re_session.search(res)
        session = match[1]

        match = re_csrf.search(res)
        csrf = match[1]

        login = utils.ask('Login:')
        passwd = utils.password('Password:')
        reason = utils.ask('Reason (optional):')

        curl = 'curl -iks -X POST %s/_odoo/support/login -d "login=%s&password=%s&reason=%s&csrf_token=%s" -H "Cookie: session_id=%s"' % (url, login, passwd, reason, csrf, session)
        stream = os.popen(curl)
        res = stream.read().strip()

        if re_error.match(res):
            raise Exception('Error logging you in, check your credentials and try again')

        match = re_session.search(res)
        session = match[1]

        if not session:
            raise Exception('Invalid session id, check your credentials and try again')

        utils.log('success', 'Successfuly logged-in to %s/_odoo/support' % (url))
        utils.log('info', 'About to download dump file for %s' % (url))

        ext = 'dump'

        if utils.confirm('Do you wish to include the filestore?'):
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

        utils.log('info', 'Downloading dump from %s/saas_worker/dump.%s to %s...' % (url, ext, destfile))
        utils.log('warning', 'This may take a while, please be patient...')

        curl = 'curl -kL %s/saas_worker/dump.%s -o %s -H "Cookie: session_id=%s"' % (url, ext, destfile, session)
        stream = os.popen(curl)
        res = stream.read().strip()

        if re_error.match(res):
            raise Exception('Error downloading dump from %sl/saas_worker/dump.%s\nMaybe the database is too big to be dumped, in which case please contact the SaaS support team and ask them for a dump of the database at %s' % (url, ext, url))

        if not os.path.isfile(destfile):
            raise Exception('Error while saving dump file to disk')

        utils.log('success', 'Successfuly downloaded dump file')

        return 0
