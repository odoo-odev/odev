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
        'format': f'%(log_color)s[%(symbol)s]{STYLE_RESET} %(message)s',
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
    },
    'extended': {
        'format': (
            f'{term.snow4}%(asctime)s{STYLE_RESET} '
            f'%(log_color)s{term.bold}[%(levelname)s]{STYLE_RESET} '
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
    }
}
