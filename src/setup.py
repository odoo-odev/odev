# -*- coding: utf-8 -*-

import configparser
import os
import shutil

from . import utils

def run():
    """
    Setup wizard for odev
    """

    utils.log('info', 'This script is about to write to different files accross your system and might need root permissions')

    odevdir = utils.ask('Where do you want to install odev?', os.getcwd())
    odoodir = utils.ask('Where do you want to store Odoo\'s repository on your machine?', '/odoo/versions')
    devdir = utils.ask('Where are you Odoo custom developments stored?', '/odoo/dev')
    dumpdir = utils.ask('Where do you want to store Odoo databases\' dump files?', '/odoo/dumps')
    dbdir = utils.ask('Where do you want to store the database-specific configuration to use with odev?', '/odoo/databases')
        
    os.makedirs(odevdir, 0o777, exist_ok=True)
    os.chmod(odevdir, 0o777)
    os.makedirs(odoodir, 0o777, exist_ok=True)
    os.chmod(odoodir, 0o777)
    os.makedirs(devdir, 0o777, exist_ok=True)
    os.chmod(devdir, 0o777)
    os.makedirs(dumpdir, 0o777, exist_ok=True)
    os.chmod(dumpdir, 0o777)
    os.makedirs(dbdir, 0o777, exist_ok=True)
    os.chmod(dbdir, 0o777)
    os.makedirs('/etc/odev', 0o777, exist_ok=True)
    os.chmod('/etc/odev', 0o777)

    try:
        if not os.path.exists('/usr/bin/odev'):
            os.symlink('%s/odev.py' % (odevdir), '/usr/bin/odev')

        if not os.path.isfile('/etc/odev/odev.cfg'):
            open('/etc/odev/odev.cfg', 'a').close()

        with open('/etc/odev/odev.cfg', 'w') as odevfile:
            odevconf = configparser.ConfigParser()
            odevconf['odev'] = {
                'Path': odevdir
            }
            odevconf['paths'] = {
                'Odoo': odoodir,
                'Devs': devdir,
                'Dumps': dumpdir,
                'Configs': dbdir
            }

            odevconf.write(odevfile)

        if odevdir != os.getcwd():
            shutil.copytree(os.getcwd(), odevdir)

    except Exception as exception:
        utils.log('error', exception)
        exit(1)