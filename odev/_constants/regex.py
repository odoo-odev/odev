import re


RE_COMMAND = re.compile(r"([/.a-zA-Z0-9_-]+\/odoo-bin.*)$")
RE_PORT = re.compile(r"(-p\s|--http-port=)([0-9]{1,5})")
RE_ODOO_DBNAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]+$")
