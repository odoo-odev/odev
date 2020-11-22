# -*- coding: utf-8 -*-

import re
import webbrowser

from . import script
from .. import utils

re_url = re.compile(r'^(https?://)?([a-zA-Z0-9-_]\.odoo\.com|localhost|127\.0\.0\.[0-9]{1,3})?')
re_id = re.compile(r'[?#]id=([0-9]{6,})')


class TaskScript(script.Script):

    def run(self, database, options):
        """
        Open the Odoo task for the provided ID in the user's default browser,
        or gives back the task's ID if an URL is given.
        """

        print(database)
        print(options)
        utils.require('ID or URL', options[1])

        if re.match(re_url, options[1]):
            match = re_id.search(options[1])
            task_id = match[1]

            utils.log('info', 'Task ID: %s' % (task_id))
        else:
            url = 'https://www.odoo.com/web#id=%s' % (options[1])
            url += '&action=333&active_id=549&model=project.task'
            url += '&view_type=form&cids=1&menu_id=4720'

            utils.log('info', 'Opening task with ID %s' % (options[1]))
            webbrowser.open(url, new=2)

        return 0
