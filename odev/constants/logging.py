# -*- coding: utf-8 -*-

from blessed import Terminal

term = Terminal()

STYLE_RESET = term.normal
SYMBOLS = {
    'NOTSET': '#',
    'DEBUG': '#',
    'INFO': 'i',
    'SUCCESS': '+',
    'QUESTION': '?',
    'WARNING': '!',
    'ERROR': '-',
    'CRITICAL': '-',
}

# Find more info about colors and styles in Blessed's documentation!
# Styles: https://blessed.readthedocs.io/en/latest/terminal.html#styles
# Colors: https://blessed.readthedocs.io/en/latest/colors.html#color-chart

THEMES = {
    'minimal': {
        'format': f'%(tree_color)s│{STYLE_RESET} %(log_color)s[%(symbol)s]{STYLE_RESET} %(message)s',
        'colors': {
            'NOTSET': term.darkgray_bold,
            'DEBUG': term.steelblue4_bold,
            'INFO': term.cyan3_bold,
            'SUCCESS': term.darkolivegreen3_bold,
            'QUESTION': term.plum3_bold,
            'WARNING': term.bright_yellow_bold,
            'ERROR': term.lightcoral_bold,
            'CRITICAL': term.white_on_lightcoral_bold,
        },
        'tree_color': {
            # Config
            'odev.commands.odoo_db.get': term.dodgerblue2,
            'odev.commands.odoo_db.set': term.dodgerblue2,
            # Exporter
            'odev.commands.exporter.scaffold': term.darkviolet,
            'odev.commands.exporter.export': term.darkviolet,
            'odev.commands.exporter.pleasedo': term.darkviolet,
            # Github
            'odev.commands.github.clone': term.steelblue1,
            # Odoo-bin
            'odev.commands.odoo_bin.cloc': term.steelblue2,
            'odev.commands.odoo_bin.run': term.steelblue2,
            'odev.commands.odoo_bin.shell': term.steelblue2,
            'odev.commands.odoo_bin.test': term.steelblue2,
            'odev.commands.odoo_bin.upgrade': term.steelblue2,
            # Odoo db
            'odev.commands.odoo_db.clean': term.springgreen3,
            'odev.commands.odoo_db.create': term.dodgerblue2,
            'odev.commands.odoo_db.dump': term.gold,
            'odev.commands.odoo_db.init': term.gray48,
            'odev.commands.odoo_db.kill': term.coral1,
            'odev.commands.odoo_db.list': term.steelblue3,
            'odev.commands.odoo_db.quickstart': term.khaki1,
            'odev.commands.odoo_db.remove': term.brown2,
            'odev.commands.odoo_db.rename': term.deeppink2,
            'odev.commands.odoo_db.restore': term.olivedrab3,
            'odev.commands.odoo_db.version': term.darkorange1,
            # Odoo Sh
            'odev.commands.odoo_sh.sh_rebuild': term.blueviolet,
            'odev.commands.odoo_sh.sh_upgrade': term.mediumpurple1,
            'odev.commands.odoo_sh.upload': term.darkviolet,
            # Utils
            'odev.utils.github': term.steelblue2,
        },
        'prefix_length' : 1,
    },
    'extended': {
        'format': (
            f'{term.snow4}%(asctime)s{STYLE_RESET} '
            f'%(tree_color)s {STYLE_RESET} %(log_color)s{term.bold}[%(levelname)s]{STYLE_RESET} '
            f'{term.maroon1}%(name)s{term.maroon1}:{STYLE_RESET} %(message)s'
        ),
        'dateformat': '%Y-%m-%d %H:%M:%S',
        'colors': {
            'NOTSET': term.darkgray,
            'DEBUG': term.steelblue4,
            'INFO': term.cyan3,
            'SUCCESS': term.darkolivegreen3,
            'QUESTION': term.plum3,
            'WARNING': term.bright_yellow,
            'ERROR': term.lightcoral,
            'CRITICAL': term.white_on_lightcoral,
        },
        'tree_color': {
            # Config
            'odev.commands.odoo_db.get': term.on_dodgerblue2,
            'odev.commands.odoo_db.set': term.on_dodgerblue2,
            # Exporter
            'odev.commands.exporter.scaffold': term.on_darkviolet,
            'odev.commands.exporter.export': term.on_darkviolet,
            'odev.commands.exporter.pleasedo': term.on_darkviolet,
            # Github
            'odev.commands.github.clone': term.on_steelblue1,
            # Odoo-bin
            'odev.commands.odoo_bin.cloc': term.on_steelblue2,
            'odev.commands.odoo_bin.run': term.on_steelblue2,
            'odev.commands.odoo_bin.shell': term.on_steelblue2,
            'odev.commands.odoo_bin.test': term.on_steelblue2,
            'odev.commands.odoo_bin.upgrade': term.on_steelblue2,
            # Odoo db
            'odev.commands.odoo_db.clean': term.on_springgreen3,
            'odev.commands.odoo_db.create': term.on_dodgerblue2,
            'odev.commands.odoo_db.dump': term.on_gold,
            'odev.commands.odoo_db.init': term.on_gray48,
            'odev.commands.odoo_db.kill': term.on_coral1,
            'odev.commands.odoo_db.list': term.on_steelblue3,
            'odev.commands.odoo_db.quickstart': term.on_khaki1,
            'odev.commands.odoo_db.remove': term.on_brown2,
            'odev.commands.odoo_db.rename': term.on_deeppink2,
            'odev.commands.odoo_db.restore': term.on_olivedrab3,
            'odev.commands.odoo_db.version': term.on_darkorange1,
            # Odoo Sh
            'odev.commands.odoo_sh.sh_rebuild': term.on_blueviolet,
            'odev.commands.odoo_sh.sh_upgrade': term.on_mediumpurple1,
            'odev.commands.odoo_sh.upload': term.on_darkviolet,
            # Utils
            'odev.utils.github': term.on_steelblue2,
        },
        'prefix_length' : 4,
    },
}
