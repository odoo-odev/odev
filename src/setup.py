# -*- coding: utf-8 -*-

import configparser
import os
import shutil

from . import utils

def run():
    """
    Setup wizard for odev
    """

    utils.log('warning', 'This script is about to write to different files accross your system and might need root permissions')

    dirs = {}

    dirs['odev'] = utils.ask('Where do you want to install odev?', os.getcwd())
    dirs['odoo'] = utils.ask('Where do you want to store Odoo\'s repositories on your machine?', '/odoo/versions')
    dirs['dev']  = utils.ask('Where do you want to store your Odoo custom developments repositories?', '/odoo/dev')
    dirs['dump'] = utils.ask('Where do you want to store Odoo databases\' dump files?', '/odoo/dumps')
        
    utils.mkdir(dirs['odev'])
    utils.mkdir(dirs['odoo'])
    utils.mkdir(dirs['dev'])
    utils.mkdir(dirs['dump'])

    try:
        paths = {
            ubin: '/usr/bin/odev',
            conf: '/etc/odev',
        }
        
        if os.path.exists(paths['ubin']):
            os.remove(paths['ubin'])
        
        os.symlink('%s/odev.py' % (dirs['odev']), paths['ubin'])

        if not os.path.isfile('%s/odev.cfg' % (paths['conf'])):
            open('%s/odev.cfg' % (paths['conf']), 'a').close()
        
        if not os.path.isfile('%s/databases.cfg' % (paths['conf'])):
            open('%s/databases.cfg' % (paths['conf']), 'a').close()

        with open('%s/odev.cfg' % (paths['conf']), 'w') as odevfile:
            odevconf = configparser.ConfigParser()
            odevconf['odev'] = {'Path': odevdir}
            odevconf['paths'] = {
                'Odoo': odoodir,
                'Devs': devdir,
                'Dumps': dumpdir
            }

            odevconf.write(odevfile)

        if odevdir != os.getcwd():
            shutil.copytree(os.getcwd(), odevdir)

    except Exception as exception:
        utils.log('error', exception)
        exit(1)
