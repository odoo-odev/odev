import requests

from odev._utils.signal import capture_signals


def get(url, params=None, cookies=None, headers=None, follow_redirects=True, stream=False):
    with capture_signals():
        return requests.get(
            url=url,
            params=params or {},
            cookies=cookies or {},
            allow_redirects=follow_redirects,
            headers=headers or {},
            stream=stream,
        )


def post(url, data=None, cookies=None, headers=None, follow_redirects=True):
    with capture_signals():
        return requests.post(
            url=url,
            data=data or {},
            cookies=cookies or {},
            allow_redirects=follow_redirects,
            headers=headers or {},
        )
