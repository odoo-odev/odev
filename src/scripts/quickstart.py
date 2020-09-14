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

    def run(self, database, options):
        """
        Creates, initializes or restores and cleanses a local database.
        """

        utils.require('version or dumpfile', options[0])

        def call(method, opts = options):
            return dispatcher.dispatcher[method].run(database, opts)

        result = call('create')

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
