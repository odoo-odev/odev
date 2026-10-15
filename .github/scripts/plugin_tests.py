#!/usr/bin/env python3
"""Test tooling shared by the test workflows of the plugins of odev.

A plugin is imported as `odev.plugins.<module>` and may rely on other plugins: its tests can only run with the
plugin and its dependencies linked into a checkout of odev. Fetches the dependencies listed in the manifests and
links everything where odev expects it. Only relies on the standard library and on `git` so that it can run before
any requirement is installed.
"""

from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path


MANIFEST_NAME = "__manifest__.py"
"""File describing a plugin, found at the root of its repository."""

REQUIREMENTS_NAME = "requirements.txt"
"""File listing the python requirements of a plugin, if any."""

PLUGINS_DIRECTORY = Path("odev") / "plugins"
"""Directory in which plugins are linked, relative to a checkout of odev."""

REPOSITORY_URL = "https://github.com/{name}.git"
"""Address from which the repository of a plugin is fetched."""


def plugin_module_name(plugin: str) -> str:
    """Convert the name of a plugin to the name of the module it is linked to under the plugins directory.

    Args:
        plugin: Name of the plugin, in the format `organization/repository`.

    Returns:
        The name of the python module for this plugin.
    """
    return plugin.split("/")[-1].replace("-", "_")


def read_dependencies(manifest: str) -> list[str]:
    """Read the plugins a plugin depends on.

    Args:
        manifest: The content of the manifest of the plugin.

    Returns:
        The names of the dependencies, in the format `organization/repository`.
    """
    for statement in ast.parse(manifest).body:
        if not isinstance(statement, ast.Assign):
            continue

        if any(isinstance(target, ast.Name) and target.id == "depends" for target in statement.targets):
            return [str(dependency) for dependency in ast.literal_eval(statement.value)]

    return []


def resolve_plugins(name: str, path: Path, fetch: Callable[[str], Path]) -> dict[str, Path]:
    """Find a plugin and all the plugins it depends on, directly or not.

    Args:
        name: Name of the plugin to test, in the format `organization/repository`.
        path: Path to the plugin to test.
        fetch: Makes a dependency available locally from its name and returns its path.

    Returns:
        The path to each plugin by name, starting with the plugin to test.
    """
    plugins: dict[str, Path] = {name: path}
    pending: list[str] = [name]

    while pending:
        manifest_path = plugins[pending.pop()] / MANIFEST_NAME

        if not manifest_path.is_file():
            continue

        for dependency in read_dependencies(manifest_path.read_text()):
            if dependency not in plugins:
                plugins[dependency] = fetch(dependency)
                pending.append(dependency)

    return plugins


def clone_plugin(name: str, directory: Path, revision: str) -> Path:
    """Clone the repository of a plugin.

    Args:
        name: Name of the plugin, in the format `organization/repository`.
        directory: Directory in which plugins are cloned.
        revision: Branch to clone, the default branch of the repository is used when it does not exist.

    Returns:
        The path to the cloned repository.
    """
    path = directory / plugin_module_name(name)
    command = ["git", "clone", "--quiet", "--depth", "1"]
    address = REPOSITORY_URL.format(name=name)
    cloned = subprocess.run([*command, "--branch", revision, address, path.as_posix()], check=False)  # noqa: S603

    if cloned.returncode:
        subprocess.run([*command, address, path.as_posix()], check=True)  # noqa: S603

    return path


def link_plugins(plugins: dict[str, Path], odev_path: Path) -> list[Path]:
    """Link plugins into a checkout of odev, where they are imported from.

    Args:
        plugins: The path to each plugin by name.
        odev_path: Path to the checkout of odev.

    Returns:
        The links created.
    """
    plugins_path = odev_path / PLUGINS_DIRECTORY
    plugins_path.mkdir(parents=True, exist_ok=True)
    links: list[Path] = []

    for name, path in plugins.items():
        link = plugins_path / plugin_module_name(name)

        if link.is_symlink():
            link.unlink()

        link.symlink_to(path.resolve(), target_is_directory=True)
        links.append(link)

    return links


def requirements_files(plugins: dict[str, Path]) -> list[Path]:
    """List the files declaring the python requirements of plugins.

    Args:
        plugins: The path to each plugin by name.

    Returns:
        The requirements files that exist.
    """
    return [path / REQUIREMENTS_NAME for path in plugins.values() if (path / REQUIREMENTS_NAME).is_file()]


def parse_arguments(arguments: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line.

    Args:
        arguments: The arguments to parse, defaults to the arguments of the process.

    Returns:
        The parsed arguments.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True, help="name of the plugin to test, as `organization/repository`")
    parser.add_argument("--plugin", required=True, type=Path, help="path to the plugin to test")
    parser.add_argument("--odev", required=True, type=Path, help="path to the checkout of odev")
    parser.add_argument("--dependencies", required=True, type=Path, help="directory in which dependencies are cloned")
    parser.add_argument("--revision", required=True, help="branch of the dependencies to test against")

    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    """Link a plugin and its dependencies into odev and print their requirements files.

    Args:
        arguments: The arguments of the command line, defaults to the arguments of the process.

    Returns:
        The exit code of the process.
    """
    options = parse_arguments(arguments)
    options.dependencies.mkdir(parents=True, exist_ok=True)

    plugins = resolve_plugins(
        options.name,
        options.plugin,
        lambda dependency: clone_plugin(dependency, options.dependencies, options.revision),
    )
    link_plugins(plugins, options.odev)

    for requirements in requirements_files(plugins):
        sys.stdout.write(f"{requirements.as_posix()}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
