# Regenerate assets files in the current database


def regenerate_assets(env):
    """Regenerate assets files in the current database."""
    assets = env["ir.attachment"].search(
        [
            "&",
            ("res_model", "=", "ir.ui.view"),
            "|",
            ("name", "=like", "%.assets_%.css"),
            ("name", "=like", "%.assets_%.js"),
        ]
    )

    count = len(assets)
    assets.unlink()
    env.cr.commit()
    return f"Deleted {count} assets files"
