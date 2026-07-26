"""Telemetry module for odev.

Reporting a command must never delay the CLI: waiting for the telemetry endpoint after a command printed its result
is directly perceptible to the user. Records are therefore written to a local spool file when a command completes,
and submitted in the background by a later odev run, which has the whole duration of its own command to do so.
"""

import json
import re
import threading
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from odev.common.config import CONFIG_DIR
from odev.common.logging import logging
from odev.common.utils import EmployeeUtils


if TYPE_CHECKING:
    from odev.common.commands.base import Command


logger = logging.getLogger(__name__)

TELEMETRY_ENDPOINT = "https://odev-telemetry.odoo.com"

# Yes, this is unsafe, we know.
# Anyway, the endpoint is public and the key is not sensitive. Worst case? Someone sends fake telemetry data.
# This is not ideal but it will already prevent most automated bots from sending fake data.
TELEMETRY_KEY = "xEGGxJLlTuRfGO8f5STWpehXKGRB8RbVpo3DgWYA7nJquh16I5Q59SU+ucyhcZoy"

REQUEST_TIMEOUT = 1
"""Timeout in seconds for a single request to the telemetry endpoint."""

MAX_SPOOLED_RECORDS = 100
"""Number of records kept in the spool file when the endpoint cannot be reached.

Old records are dropped past this limit so that a long-lasting outage cannot grow the file indefinitely.
"""


class TelemetryRun:
    """Handle on the telemetry record of a single command.

    The record is only complete once the command finished, since it carries its exit code and execution time.
    Callers must therefore signal completion through :meth:`finish`, which spools the record for submission.
    """

    def __init__(self, telemetry: "Telemetry", payload: dict[str, Any]):
        self.telemetry: Telemetry = telemetry
        """Telemetry manager this record belongs to."""

        self.payload: dict[str, Any] = payload
        """Data describing the command being reported."""

    def finish(self, exit_code: int = 0, execution_time: float = 0.0) -> None:
        """Complete the record with the outcome of the command and spool it for submission.

        :param exit_code: Exit code of the command.
        :param execution_time: Time the command took to run, in minutes.
        """
        self.telemetry.spool(
            {
                "payload": self.payload,
                "exit_code": exit_code,
                "execution_time": execution_time,
            }
        )


class Telemetry:
    """Telemetry manager."""

    def __init__(self, odev):
        self.odev = odev

    @property
    def spool_path(self) -> Path:
        """Path to the file holding the telemetry records awaiting submission."""
        return CONFIG_DIR / f"{self.odev.name}-telemetry.jsonl"

    def _get_client_id(self) -> str:
        """Get or generate the client ID."""
        client_id = self.odev.config.telemetry.client_id

        if not client_id:
            client_id = str(uuid.uuid4())
            self.odev.config.telemetry.client_id = client_id

        return client_id

    def _is_employee(self) -> bool:
        """Check if the user is an Odoo employee."""
        return EmployeeUtils(self.odev).is_employee()

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

    def _send_request(self, path: str, payload: dict) -> dict[str, Any] | None:
        """Send telemetry data to the given endpoint and return the decoded response.

        :param path: Path of the endpoint to send the data to.
        :param payload: Data to send.
        :return: The decoded response, or None if the data could not be sent.
        """
        try:
            with urlopen(self._prepare_request(path, payload), timeout=REQUEST_TIMEOUT) as response:  # noqa: S310
                return json.loads(response.read())
        except (URLError, OSError) as error:
            logger.debug(f"Telemetry failed: {error}")
        except json.JSONDecodeError as error:
            logger.debug(f"Telemetry returned an invalid response: {error}")

        return None

    def _sanitize_arguments(self, command: "Command") -> tuple[str, str]:
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

    def send(self, command: "Command") -> TelemetryRun | None:
        """Start recording the execution of a command.

        The returned handle must be completed through :meth:`TelemetryRun.finish` once the command is done, so that
        its exit code and execution time are recorded as well.

        :param command: The command being run.
        :return: A handle on the record, or None if this command must not be reported.
        """
        if len(self.odev._command_stack) != 1 or self.odev.in_test_mode:
            return None

        enabled = self.odev.config.telemetry.enabled
        payload = {
            "client_id": self._get_client_id(),
            "is_telemetry_agreed": enabled,
        }

        if enabled:
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

        return TelemetryRun(self, payload)

    def spool(self, record: dict[str, Any]) -> None:
        """Append a record to the spool file, to be submitted by a later run.

        :param record: The record to spool.
        """
        try:
            self.spool_path.parent.mkdir(parents=True, exist_ok=True)

            with self.spool_path.open("a", encoding="utf-8") as spool:
                spool.write(json.dumps(record) + "\n")
        except OSError as error:
            logger.debug(f"Failed to spool telemetry: {error}")

    def flush(self) -> None:
        """Submit the records spooled by previous runs in a background thread.

        The thread is a daemon: whatever it did not manage to send stays in the spool and is retried by the next
        run, so that exiting odev never waits on the telemetry endpoint.
        """
        if self.odev.in_test_mode or not self.spool_path.is_file():
            return

        threading.Thread(target=self._flush, name="odev-telemetry", daemon=True).start()

    def _flush(self) -> None:
        """Submit every spooled record, keeping in the spool the ones that could not be sent."""
        records = self._claim_spooled_records()

        if not records:
            return

        logger.debug(f"Submitting {len(records)} spooled telemetry records")
        unsent = [record for record in records if not self._submit(record)]

        if unsent:
            self._respool(unsent)

    def _claim_spooled_records(self) -> list[dict[str, Any]]:
        """Read the spooled records and empty the spool file so that they are not submitted twice.

        :return: The records that were waiting in the spool.
        """
        records: list[dict[str, Any]] = []

        try:
            with self.spool_path.open("r+", encoding="utf-8") as spool:
                lines = spool.readlines()
                spool.seek(0)
                spool.truncate()
        except OSError as error:
            logger.debug(f"Failed to read spooled telemetry: {error}")
            return records

        for line in lines:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                logger.debug(f"Discarding malformed telemetry record: {line.strip()!r}")

        return records

    def _respool(self, records: list[dict[str, Any]]) -> None:
        """Put records that could not be submitted back into the spool.

        :param records: The records to keep for a later run.
        """
        for record in records[-MAX_SPOOLED_RECORDS:]:
            self.spool(record)

    def _submit(self, record: dict[str, Any]) -> bool:
        """Submit a single spooled record to the telemetry endpoint.

        :param record: The record to submit.
        :return: Whether the record was submitted successfully.
        """
        response = self._send_request("odev/telemetry", record["payload"])

        if response is None:
            return False

        line_id = response.get("result", {}).get("id")

        if line_id is None or not record["payload"].get("is_telemetry_agreed"):
            return True

        self._send_request(
            "odev/telemetry/update",
            {
                "telemetry_id": line_id,
                "exit_code": record["exit_code"],
                "execution_time": record["execution_time"],
            },
        )

        return True
