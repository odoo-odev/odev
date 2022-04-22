import json
import os
import re
from argparse import Namespace

from odev.commands.odoo_db.code import VSCodeDebugConfigCommand


UPGRADE_PATH_PATTERN = re.compile(r"^--upgrade-path=(.+$)")


def test_valid_config():
    args = Namespace(
        database="test_db",
        assume_yes=True,
        assume_no=False,
        log_level="WARNING",
    )

    def sanitize(vscode_json_str):
        lines = []
        # vscode json contains invalid comments
        for line in vscode_json_str.splitlines():
            if line.strip()[:2] == "//":
                continue
            else:
                lines.append(line)
        return "\n".join(lines)

    def get_config_dict(kwargs):
        nonlocal args
        command = VSCodeDebugConfigCommand(args)
        raw_vscode_json = command.render_debug_template(os.path.dirname(__file__), **kwargs)
        return json.loads(sanitize(raw_vscode_json))

    def assert_config(kwargs, should_have_upgrade_path=False):
        debug_config_dict = get_config_dict(kwargs)

        assert len(debug_config_dict["configurations"]) == 2, "should have two configs"

        for config in debug_config_dict["configurations"]:  # noqa: B007
            assert args.database in config["args"], "should contain db name"
            has_upgrade_path = any(UPGRADE_PATH_PATTERN.match(arg) for arg in config["args"])
            have_or_not = "" if should_have_upgrade_path else "not "
            assert not should_have_upgrade_path ^ has_upgrade_path, f"should {have_or_not}have upgrade path"

            if should_have_upgrade_path:
                for arg in config["args"]:
                    match = UPGRADE_PATH_PATTERN.match(arg)
                    if match:
                        migrations_dir = match.group(1)
                        assert os.path.basename(migrations_dir) == "migrations", "path should end with 'migrations'"

    kwargs = {"version": "42"}
    assert_config(kwargs)
    kwargs.update({"upgrade_repo_path": os.path.dirname(__file__)})
    assert_config(kwargs, True)
