# Regenerate assets files in the current database


def regenerate_assets(env):
    """Regenerate assets files in the current database."""
    # Delete custom assets from ir_asset if the table exists
    env.cr.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'ir_asset')")
    if env.cr.fetchone()[0]:
        env.cr.execute("DELETE FROM ir_asset WHERE path LIKE '%_custom/%'")

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
