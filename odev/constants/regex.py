# -*- coding: utf-8 -*-

import re

RE_VERSION = re.compile(r'^([a-z~0-9]+\.[0-9]+)')
RE_COMMAND = re.compile(r'([/.a-zA-Z0-9_-]+\/odoo-bin.*)$')
RE_PORT = re.compile(r'(-p\s|--http-port=)([0-9]{1,5})')
RE_ODOO_DBNAME = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_.-]+$')
