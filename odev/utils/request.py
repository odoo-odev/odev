# -*- coding: utf-8 -*-

import re
import requests

from odev.utils.signal import capture_signals


def get(url, params={}, cookies={}, headers={}, follow_redirects=True):
    with capture_signals():
        return requests.get(
            url=url,
            params=params,
            cookies=cookies,
            allow_redirects=follow_redirects,
            headers=headers,
        )


def post(url, data={}, cookies={}, headers={}, follow_redirects=True):
    with capture_signals():
        return requests.post(
            url=url,
            data=data,
            cookies=cookies,
            allow_redirects=follow_redirects,
            headers=headers,
        )
