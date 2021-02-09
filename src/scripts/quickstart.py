# -*- coding: utf-8 -*-

import re
import os
from datetime import datetime
import shutil

from . import script, dispatcher
from .. import utils

re_version = re.compile(r'^([a-z~0-9]+\.[0-9]+)')
re_url = re.compile(r'^(https?://)?([a-zA-Z0-9-_]\.odoo\.com|localhost|127\.0\.0\.[0-9]+)?')


class QuickStartScript(script.Script):

    usage = 'quickstart <database> <version|path|url>'
    alias = ['qs']
    args = [
        ['database', 'Name of the local database to create'],
        ['version ', 'Calls odev init and deploys an empty database'],
        ['path    ', 'Attempts to restore a local file to the new database (the file must be a valid database dump)'],
        ['url     ', 'Downloads a dump of an Odoo SaaS or SH database and restores it locally']
    ]
    description = """
Quickly and easlily setups a database. This performs the following actions:
- Creates a new, empty database
- Initializes, dumps and restores or restores an existing dump to the new database
- Cleanses the database so that it can be used for development
"""

    def run(self, database, options):
        """
        Creates, initializes or restores and cleanses a local database.
        """

        utils.require('version or dumpfile', options[0])

        def call(method, opts=options):
            return dispatcher.dispatcher[method].run(database, opts)

        result = call('create', [None] if re_version.match(options[0]) or re_url.match(options[0]) else options)

        try:
            if result == 0:
                if re_version.match(options[0]):
                    result = call('init')
                else:
                    if re_url.match(options[0]):
                        result = call('dump', [options[0], '/tmp/odev'])

                    if result == 0:
                        file = '/tmp/odev/%s_%s.dump.' % (datetime.now().strftime('%Y%m%d'), database)
                        ext = 'zip'

                        if not os.path.isfile('%s%s' % (file, ext)):
                            ext = 'dump'

                        if not os.path.isfile('%s%s' % (file, ext)):
                            raise Exception('An error occured while fetching dump file at \'%s%s\'' % (file, ext))

                        result = call('restore', ['%s%s' % (file, ext)])

                        if result == 0:
                            result = call('clean')

        except Exception as exception:
            utils.log('error', 'An error occured, cleaning up files and removing database:')
            utils.log('error', exception)
            call('remove')
            result = 1
        finally:
            if os.path.isdir('/tmp/odev'):
                shutil.rmtree('/tmp/odev')

        return result
