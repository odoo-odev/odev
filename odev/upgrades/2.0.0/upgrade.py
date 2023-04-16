from odev.common.config import ConfigManager


def run():
    config = ConfigManager("odev")

    default_saas_repos = [
        "odoo-ps/psbe-custom",
        "odoo/ps-custom",
        "odoo-ps/psae-custom",
        "odoo-ps/pshk-custom",
        "odoo-ps/psus-custom",
    ]

    config.set("repos", "saas_repos", ",".join(default_saas_repos))
    config.save()
