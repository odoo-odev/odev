import json
import re
import tempfile
from argparse import Namespace
from collections import defaultdict
from pathlib import Path
from typing import Dict, Optional

import pytest

from odev._utils.config import ConfigManager
from odev.commands.odoo_db.code import VSCodeDebugConfigCommand
from odev.structures.commands import LocalDatabaseCommand


CUSTOM_MODULE_NAMES = ["psbe_rockz", "code_or_no_code"]


@pytest.fixture(autouse=True)
def mock_database(monkeypatch):
    def check_database(*args, **kwargs):
        return None

    def db_version_clean(*args, **kwargs):
        return "42"

    monkeypatch.setattr(LocalDatabaseCommand, "check_database", check_database)
    monkeypatch.setattr(LocalDatabaseCommand, "db_version_clean", db_version_clean)


@pytest.fixture(autouse=True)
def mock_config(monkeypatch):
    mocked_config_storage: Dict[str, Dict[str, str]] = defaultdict(dict)

    def _get(self, section, key, default=None):
        return mocked_config_storage[section].get(key, default)

    def _set(self, section, key, value):
        mocked_config_storage[section][key] = value

    monkeypatch.setattr(ConfigManager, "get", _get)
    monkeypatch.setattr(ConfigManager, "set", _set)


@pytest.fixture
def args(mock_root_dir):
    psbe_custom_test_repo = Path(mock_root_dir, "psbe-test-repo")
    return Namespace(
        database="test_db",
        repo=psbe_custom_test_repo,
        assume_yes=True,
        assume_no=False,
        log_level="WARNING",
    )


@pytest.fixture
def mock_root_dir():
    with tempfile.TemporaryDirectory("odev_test") as temp_dir:
        custom_project_repo_path = Path(temp_dir, "psbe-test-repo")
        for upgrade_repo in ["custom_upgrade", "upgrade"]:
            fullpath = Path(temp_dir, upgrade_repo)
            if not fullpath.exists():
                migrations_dir = fullpath / "migrations"
                migrations_dir.mkdir(parents=True)

        for module_dir in CUSTOM_MODULE_NAMES + ["util_package"]:
            (custom_project_repo_path / module_dir).mkdir(parents=True)

        yield temp_dir


@pytest.fixture
def code_command(args, mock_root_dir):
    return VSCodeDebugConfigCommand(args)


def test_launch_json_no_upgrade_repo_args_no_config(code_command):
    config = Config()
    upgrade_repo_parameter_to_path_keys = {"upgrade_repo_path", "custom_util_repo_path"}
    for repo_parameter in upgrade_repo_parameter_to_path_keys:
        assert config.get("paths", repo_parameter) is None, "should have no upgrade repo paths in config"
    assert_config(code_command)


def test_launch_json_no_upgrade_repo_args_config(args, mock_root_dir):
    config = Config()
    upgrade_repo_path_from_config = Path(mock_root_dir, "upgrade")
    config.set("paths", "upgrade_repo_path", upgrade_repo_path_from_config)

    command = VSCodeDebugConfigCommand(args)
    assert_config(command, upgrade_repo_path_from_config)


def test_launch_json_upgrade_repo_args_no_config(args, mock_root_dir):
    config = Config()
    upgrade_repo_parameter_to_path_keys = {"upgrade_repo_path", "custom_util_repo_path"}
    for repo_parameter in upgrade_repo_parameter_to_path_keys:
        assert config.get("paths", repo_parameter) is None, "should have no upgrade repo paths in config"

    upgrade_repo_path_from_args = Path(mock_root_dir, "upgrade")
    args.upgrade_repo_path = upgrade_repo_path_from_args
    command = VSCodeDebugConfigCommand(args)
    assert_config(command, upgrade_repo_path_from_args)


def test_launch_json_upgrade_repo_args_config(args, mock_root_dir):
    # args have priority over config and should overwrite them
    config = Config()
    upgrade_repo_path_from_config = Path(mock_root_dir, "outdated_upgrade_dir")
    config.set("paths", "upgrade_repo_path", upgrade_repo_path_from_config)

    upgrade_repo_path_from_args = Path(mock_root_dir, "upgrade")
    args.upgrade_repo_path = upgrade_repo_path_from_args
    command = VSCodeDebugConfigCommand(args)
    assert_config(command, upgrade_repo_path_from_args)

    assert upgrade_repo_path_from_args == Path(
        config.get("paths", "upgrade_repo_path")
    ), "args should have overwritten outdated config value"


def assert_config(code_command: VSCodeDebugConfigCommand, upgrade_repo_path: Optional[Path] = None):
    should_have_upgrade_path = bool(upgrade_repo_path)
    debug_config_dict = get_dict_from_rendered_json(code_command, "launch.json")

    assert len(debug_config_dict["configurations"]) == 3, "should have 3 configs"

    upgrade_path_arg_pattern = re.compile(r"^--upgrade-path=(.+$)")
    addons_arg_pattern = re.compile(r"^--addons-path=(.+$)")
    for config in debug_config_dict["configurations"]:  # noqa: B007
        assert any(
            re.match(rf"{code_command.args.database}(_empty)?", arg) for arg in config["args"]
        ), "should contain db name"
        has_upgrade_path = any(upgrade_path_arg_pattern.match(arg) for arg in config["args"])
        have_or_not = "" if should_have_upgrade_path else "not "
        assert not (should_have_upgrade_path ^ has_upgrade_path), f"should {have_or_not}have upgrade path"

        for i, arg in enumerate(config["args"]):
            upgrade_path_match = upgrade_path_arg_pattern.match(arg)
            if upgrade_path_match:
                migrations_path = Path(upgrade_path_match.group(1))
                assert migrations_path.name == "migrations", "path should end with 'migrations'"
                assert migrations_path.parent == upgrade_repo_path, "should match upgrade path"
                continue

            addons_match = addons_arg_pattern.match(arg)
            if addons_match:
                addons_paths = set(addons_match.group(1).split(","))
                assert addons_paths >= {
                    "addons",
                    "../enterprise",
                    "../design-themes",
                }, "should contain (at least) std/enterprise addons paths"
                continue

            if arg in ["-u", "-i"]:
                custom_modules = set(config["args"][i + 1].split(","))
                assert custom_modules == set(
                    CUSTOM_MODULE_NAMES
                ), f"should only contains custom modules [{CUSTOM_MODULE_NAMES}]"
                assert "util_package" not in custom_modules, "should not contain util_package"
                continue


def test_task_json(code_command):
    tasks_data = get_dict_from_rendered_json(code_command, "tasks.json")

    assert "version" in tasks_data, "should contain 'version' key"

    tasks = tasks_data.get("tasks")
    assert tasks, "should contain 'tasks' key"
    assert isinstance(tasks, list)
    assert all(isinstance(task, dict) for task in tasks)
    assert len(tasks) >= 2 and len(tasks) <= 3, "should have either 2 or 3 tasks defined"
    assert all(
        len({"label", "dependsOn", "type"} & task.keys()) == 2 for task in tasks
    ), "each task should have label and either dependsOn or type as keys"


def test_filestructure(code_command, args, mock_root_dir):
    root = Path(mock_root_dir)

    code_command.run()

    vscode_config_dir = root / args.repo / ".vscode"
    assert vscode_config_dir.is_dir(), "should contains .vscode directory"
    assert (vscode_config_dir / "tasks.json").is_file(), "should contain tasks.json"
    assert (vscode_config_dir / "launch.json").is_file(), "should contain launch.json"


# Test helper functions


def sanitize(vscode_json_str):
    lines = []
    # vscode json contains invalid comments
    for line in vscode_json_str.splitlines():
        if line.strip()[:2] == "//":
            continue
        else:
            lines.append(line)
    return "\n".join(lines)


def get_dict_from_rendered_json(command: VSCodeDebugConfigCommand, filename: str):
    render_kwargs = command.get_render_kwargs()

    raw_vscode_json = command.render_debug_template(filename, **render_kwargs)
    return json.loads(sanitize(raw_vscode_json))
