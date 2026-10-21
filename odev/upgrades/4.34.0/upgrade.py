"""Upgrade to odev 4.34.0.

Remove the options saved as the text "None" in the configuration file.

Filling in the defaults used to write an option whose default is `None` as "None", which every later run read
back as a real value: for instance the knowledge index of odev-plugin-ai-upgrade then believed it was configured
with a repository named "None". Removing those options brings back their actual default.
"""

from odev.common.logging import logging
from odev.common.odev import Odev


logger = logging.getLogger(__name__)


def run(odev: Odev) -> None:
    parser = odev.config.parser

    for section in parser.sections():
        for option, value in parser.items(section, raw=True):
            if value == "None":
                logger.debug(f"Removing option '{section}.{option}' saved as 'None'")
                parser.remove_option(section, option)

    odev.config.save()
