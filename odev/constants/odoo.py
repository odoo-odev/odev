ODOO_MANIFEST_NAMES = [
    "__manifest__.py",
    "__openerp__.py",
]

ODOO_ADDON_PATHS = [
    "/enterprise",
    "/design-themes",
    "/odoo/odoo/addons",
    "/odoo/addons",
]

ODOO_REPOSITORIES = [
    "odoo",
    "enterprise",
    "design-themes",
]

ODOO_UPGRADE_REPOSITORIES = [
    "upgrade",
    "upgrade-specific",
    "upgrade-platform",
]

ODOO_MASTER_REPO = "/master/"

PRE_11_SAAS_TO_MAJOR_VERSIONS = {
    saas_version: major_version
    for major_version, (saas_v_start, saas_v_end) in {7: (1, 5), 8: (6, 6), 9: (7, 13), 10: (14, 18)}.items()
    for saas_version in range(saas_v_start, saas_v_end + 1)
}
