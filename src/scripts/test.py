# -*- coding: utf-8 -*-

import configparser

from . import script
from .. import utils


class TestScript(script.Script):
    
    def run(self, database, options):
        """
        Runs all available methods for getting information about a database.
        """

        config = configparser.ConfigParser()
        config.read('/etc/odev/odev.cfg')
        print(config.sections())

        result = self.db_list()
        utils.log('info', 'db_list(): %s' % (result))

        result = self.db_list_all()
        utils.log('info', 'db_list_all(): %s' % (result))

        result = self.db_exists(database)
        utils.log('info', 'db_exists(): %s' % (result))

        result = self.db_exists_all(database)
        utils.log('info', 'db_exists_all(): %s' % (result))

        result = self.db_version(database)
        utils.log('info', 'db_version(): %s' % (result))

        result = self.db_version_clean(database)
        utils.log('info', 'db_version_clean(): %s' % (result))

        result = self.db_version_full(database)
        utils.log('info', 'db_version_full(): %s' % (result))
        
        result = self.db_enterprise(database)
        utils.log('info', 'db_enterprise(): %s' % (result))

        result = self.db_runs(database)
        utils.log('info', 'db_runs(): %s' % (result))

        result = self.db_pid(database)
        utils.log('info', 'db_pid(): %s' % (result))

        result = self.db_command(database)
        utils.log('info', 'db_command(): %s' % (result))

        result = self.db_port(database)
        utils.log('info', 'db_port(): %s' % (result))

        result = self.db_url(database)
        utils.log('info', 'db_url(): %s' % (result))

        result = self.db_filestore(database)
        utils.log('info', 'db_filestore(): %s' % (result))

        return 0
