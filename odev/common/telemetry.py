"""Telemetry module for odev."""

import json
import re
import threading
import uuid
from queue import Queue
from subprocess import CalledProcessError
from time import monotonic
from urllib.error import URLError
from urllib.request import Request, urlopen

from odev.common import bash
from odev.common.commands.base import Command
from odev.common.logging import logging


logger = logging.getLogger(__name__)

TELEMETRY_ENDPOINT = "https://ps-tools-staging.odoo.com"
TELEMETRY_KEY = "changeme"


class Telemetry:
    """Telemetry manager."""

    def __init__(self, odev):
        self.odev = odev

    def _get_client_id(self) -> str:
        """Get or generate the client ID."""
        client_id = self.odev.config.telemetry.client_id

        if not client_id:
            client_id = str(uuid.uuid4())
            self.odev.config.telemetry.client_id = client_id

        return client_id

    def _is_employee(self) -> bool:
        """Check if the user is an Odoo employee."""
        secret = self.odev.store.secrets.get("accounts.odoo.com", ["login"], scope="user", ask_missing=False)

        if secret:
            return secret.login.endswith("@odoo.com")

        try:
            process = bash.execute("git config user.email")

            if not process:
                return False

            email = process.stdout.decode().strip()
            return email.endswith("@odoo.com")
        except (CalledProcessError, UnicodeDecodeError):
            return False

    def _prepare_request(self, path: str, payload: dict) -> Request:
        """Prepare a request to send telemetry data."""
        jsonrpc = {"jsonrpc": "2.0", "method": "call", "params": payload, "id": 1}
        data = json.dumps(jsonrpc).encode("utf-8")
        return Request(  # noqa: S310
            f"{TELEMETRY_ENDPOINT}/{path}",
            method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {TELEMETRY_KEY}"},
            data=data,
        )

    def _sanitize_arguments(self, command: Command) -> tuple[str, str]:
        """Sanitize arguments for telemetry so that sensitive data is not sent."""
        arguments = " ".join(command._argv) if command._argv else ""
        additional_args = ""

        for arg in command._arguments.values():
            arg_name = arg["name"]
            if not hasattr(command.args, arg_name):
                continue

            aliases = command._arguments.get(arg_name, {}).get("aliases", [])
            positional = not any(alias.startswith("-") for alias in aliases)

            if positional:
                arg_value = getattr(command.args, arg_name)

                if not arg_value:
                    continue

                if isinstance(arg_value, list):
                    arg_value = ",".join(arg_value)

                arguments = arguments.replace(str(arg_value), f"<{arg_name}>", 1)
            elif aliases:
                aliases_str = "|".join(aliases)
                pattern = rf"(?:{aliases_str})(?:=|\s+)(?P<value>\S+)"
                search_result = re.search(pattern, arguments)

                if search_result:
                    arguments = arguments.replace(search_result.group("value"), f"<{arg_name}>", 1)

        return arguments, additional_args

    def send(self, command: Command) -> tuple[threading.Thread, Queue] | None:
        """Send telemetry data."""
        if len(self.odev._command_stack) != 1:
            return None

        payload = {
            "client_id": self._get_client_id(),
            "is_telemetry_agreed": self.odev.config.telemetry.enabled,
        }

        if self.odev.config.telemetry.enabled:
            args, additional_args = self._sanitize_arguments(command)
            payload.update(
                {
                    "is_employee": self._is_employee(),
                    "cmd_name": command._name,
                    "arguments": args,
                    "additional_arguments": additional_args,
                    "version": self.odev.version,
                    "branch": self.odev.git.branch or "<detached>",
                    "plugin_name": command.__module__.split(".")[2]
                    if command.__module__.startswith("odev.plugins.")
                    else False,
                }
            )

        def _send(_queue: Queue):
            try:
                request = self._prepare_request("odev/telemetry", payload)

                with urlopen(request, timeout=2) as response:  # noqa: S310
                    content = response.read()

                result = json.loads(content).get("result", {}).get("id")
                _queue.put(result)
            except (URLError, OSError) as e:
                logger.debug(f"Telemetry failed: {e}")
                _queue.put(None)

        queue = Queue(maxsize=1)
        thread = threading.Thread(target=_send, args=(queue,))
        thread.start()
        return thread, queue

    def update(self, line_id: int) -> None:
        """Update a specific line in the telemetry data."""
        payload = {
            "telemetry_id": line_id,
            "exit_code": 0,
            "execution_time": (monotonic() - self.odev.start_time) / 60,
        }

        def _update():
            try:
                request = self._prepare_request("odev/telemetry/update", payload)

                with urlopen(request, timeout=1):  # noqa: S310
                    pass
            except (URLError, OSError) as e:
                logger.debug(f"Telemetry failed: {e}")

        threading.Thread(target=_update).start()
