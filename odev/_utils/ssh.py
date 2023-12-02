import re
from time import sleep
from typing import Tuple

import paramiko
from scp import SCPClient

from odev._utils import logging


re_url = re.compile(r"@?([\w.-]+):?")


logging.getLogger("paramiko").setLevel(logging.logging.WARNING)


class SSHClient:
    """
    Wrapper class for easy access to remote SSH systems.
    Fetches SSH identity keys from a running SSH agent if available,
    or defaults to available SSH key files.
    """

    client: paramiko.SSHClient
    url: str
    username: str
    stdin: paramiko.Channel
    stdout: paramiko.Channel

    def __init__(self, url: str, username: str = None):
        """
        Initialize a new SSH client.
        """

        self.url, self.username = self._get_connection_info(url, username)
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    def __enter__(self):
        self.client.connect(self.url, username=self.username)

        # Quick hack/patch to speed up data transfer and keep session alive
        transport = self.client.get_transport()
        assert transport

        transport.default_window_size = 3 * (1024**2)
        transport.packetizer.REKEY_BYTES = pow(2, 40)
        transport.packetizer.REKEY_PACKETS = pow(2, 40)
        transport.set_keepalive(10)

        # Wait for the handshake to fully complete and avoid timing errors
        # when sending commands too early
        sleep(0.1)

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return self.client.close()

    @classmethod
    def test_url(cls, url: str):
        return bool(re_url.match(url))

    def _get_connection_info(self, url: str, username: str = None) -> Tuple[str, str]:
        match_url = re_url.findall(url)

        if not match_url:
            raise ValueError("Invalid URL provided for SSH connection")

        if not username:
            if "@" in url:
                # Try to guess username from ssh-compatible auth string
                re_username = re.compile(r"^([^@]+)")
                match_username = re_username.findall(url)
            else:
                # Try to guess username based on build ID on Odoo SH
                re_build = re.compile(r"-([\d]+).dev.odoo.com")
                match_username = re_build.findall(url)

            if not match_username:
                raise ValueError("No username provided for SSH connection")

            username = match_username[~0]

        assert isinstance(match_url[~0], str)
        assert isinstance(username, str)
        return match_url[~0], username

    def exec(self, command: str) -> str:
        """
        Execute a command on the remote system and returns its output.
        """
        _, stdout, stderr = self.client.exec_command(command)
        error = stderr.read()

        if error:
            raise Exception(error.decode("utf-8"))

        return stdout.read().decode("utf-8")

    def download(self, path_from: str, path_to: str = None):
        """
        Download a file using SCP.
        """
        with SCPClient(self.client.get_transport()) as client:
            client.get(remote_path=path_from, local_path=path_to)

    def upload(self, path_from: str, path_to: str = None):
        """
        Upload a file using SCP.
        """
        with SCPClient(self.client.get_transport()) as client:
            client.put(files=path_from, remote_path=path_to)
