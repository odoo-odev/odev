# -*- coding: utf-8 -*-

import os


# TODO: move to requests library
def curl(url, *args, include_response_headers=True, follow_redirects=True, silent=True):
    options = ['-k']
    if include_response_headers:
        options.append('-i')
    if follow_redirects:
        options.append('-L')
    if silent:
        options.append('-s')
    compiled_args = ' '.join(options + list(args))
    cmdline = f'curl {compiled_args} `{url}`'
    stream = os.popen(cmdline)
    return stream.read().strip()
