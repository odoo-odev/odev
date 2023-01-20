from copier import copy


def fetch_pre_commit_config(dst_path, version):
    """Helper to fetch the standard pre-commit config"""
    config_repo = "odoo-ps/psbe-ps-tech-tools.git"
    vcs_ref = f"{version}-pre-commit-config"
    copy(
        f"git@github.com:{config_repo}",
        dst_path=dst_path,
        vcs_ref=vcs_ref,
        force=True,
        quiet=True,
    )
