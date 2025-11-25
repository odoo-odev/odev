"""Configure self-update behavior."""

from odev.common.console import console
from odev.common.logging import logging
from odev.common.odev import Odev


logger = logging.getLogger(__name__)


PRIORITY = 60


# --- Setup --------------------------------------------------------------------


def setup(odev: Odev) -> None:
    """Configure telemetry behavior."""
    logger.info(
        """
        Odev can send anonymous usage data to help us improve odev using telemetry
        We only collect the command name and arguments, the exit code, and the execution time of each command run,
        and the current version of odev. Sensitive arguments are ignored as to protect your and your customers' privacy
        """
    )

    in_config = hasattr(odev.config, "telemetry")
    enabled = console.confirm(
        "Do you want to send telemetry data?",
        default=odev.config.telemetry.enabled if in_config else True,
    )

    if enabled is not None:
        if in_config:
            odev.config.telemetry.enabled = enabled
        else:
            # During the upgrade process - when adding the telemetry feature - the config parser is not initialized
            # with the new section so we need to add it manually
            odev.config.parser.add_section("telemetry")
            odev.config.parser.set("telemetry", "enabled", str(enabled))

            with odev.config.path.open("w") as file:
                odev.config.parser.write(file)

    if enabled:
        logger.info("You can opt out at any time by running `odev config telemetry.enabled false`")
    else:
        logger.info("You can opt in at any time by running `odev config telemetry.enabled true`")
