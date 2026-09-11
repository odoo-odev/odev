"""Discovery of the plugins odev loads, rooted in a single source of truth.

A plugin is a symbolic link under the plugins directory, and nothing else. The link's own name is the python module
the plugin is imported as, while the directory it points to gives the plugin its `organization/repository` identity.
Enabling a plugin is therefore creating that link and disabling it is removing it, with no second record to keep in
sync: the filesystem also enforces that two plugins can never claim the same module name, as the link would already
exist.

Discovery never imports nor executes anything from a plugin and never raises: a plugin that cannot be read, whose
dependencies are missing or that takes part in a dependency cycle is reported and left out, so that one broken
repository can never keep odev from running.
"""

import ast
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, NamedTuple, TypedDict

from odev.common.logging import logging


__all__ = [
    "PLUGIN_MANIFEST_FILENAME",
    "Discovery",
    "Manifest",
    "Plugin",
    "SkippedPlugin",
    "forget_plugins",
    "installed_plugins",
    "parse_plugin_manifest",
    "plugin_identity",
    "plugin_link",
    "plugin_module_name",
    "plugins_requiring",
    "read_plugin_manifest",
]


logger = logging.getLogger(__name__)


PLUGIN_MANIFEST_FILENAME = "__manifest__.py"
"""Name of the manifest file located at the root of a plugin repository."""


class Manifest(TypedDict):
    """Plugin manifest information."""

    name: str
    description: str
    version: str
    depends: list[str]


class Plugin(NamedTuple):
    """A plugin odev loads, as described by its link under the plugins directory."""

    name: str
    """Name of the plugin, in the format `organization/repository`."""

    path: Path
    """Path to the link under the plugins directory, from which the module name is taken."""

    manifest: Manifest
    """Manifest read from the repository the link points to."""

    @property
    def module(self) -> str:
        """Name of the python module this plugin is imported as.

        Module names must be valid python identifiers even when the link they come from uses dashes, so that other
        plugins can reach this one with a plain `import odev.plugins.<module>`.
        """
        return self.path.name.replace("-", "_")

    @property
    def target(self) -> Path:
        """Path to the repository the link points to."""
        return self.path.resolve()


class SkippedPlugin(NamedTuple):
    """A plugin that is installed but that odev could not load."""

    name: str
    """Name of the plugin, in the format `organization/repository`."""

    path: Path
    """Path to the link under the plugins directory."""

    reason: str
    """Why the plugin was left out, phrased to follow "Ignoring plugin 'x':"."""


class Discovery(NamedTuple):
    """Everything one read of the plugins directory found."""

    loaded: list[Plugin]
    """The plugins to import, the first one being the first that needs to be imported."""

    skipped: list[SkippedPlugin]
    """The plugins that are installed but could not be loaded, sorted by name."""

    installed: list[Plugin]
    """Every plugin whose manifest could be read, whether it ended up loaded or skipped, sorted by name.

    Loading a plugin and being installed are two different things: a plugin left out because a dependency of its
    own is missing is still installed, and still depends on what it depends on.
    """


def plugin_module_name(plugin: str) -> str:
    """Convert the name of a plugin to the name of the module it is linked to under the plugins directory.

    :param plugin: Name of the plugin, in the format `organization/repository`
    :return: Name of the python module for this plugin
    """
    return plugin.split("/")[-1].replace("-", "_")


def plugin_identity(target: Path) -> str:
    """Derive the `organization/repository` name of a plugin from the repository its link points to.

    :param target: Path to the repository the link of the plugin points to
    :return: Name of the plugin, in the format `organization/repository`
    """
    return f"{target.parent.name}/{target.name}"


def parse_plugin_manifest(source: str, name: str) -> Manifest | None:
    """Extract the metadata of a plugin from the source of its manifest, without executing it.

    Only the module docstring and top-level assignments of literal values are read, which makes this function safe
    to use on manifests originating from untrusted repositories. A source that does not define a top-level
    `__version__` string is not considered a valid odev plugin manifest.

    :param source: Content of the `__manifest__.py` file
    :param name: Name of the plugin, in the format `organization/repository`
    :return: Manifest of the plugin, or `None` if the source is not a valid odev plugin manifest
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        logger.debug(f"Failed to parse the manifest of plugin {name!r}")
        return None

    assignments: dict[str, Any] = {}

    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue

        try:
            literal = ast.literal_eval(value)
        except (SyntaxError, TypeError, ValueError, MemoryError, RecursionError):
            continue

        assignments.update({target.id: literal for target in targets if isinstance(target, ast.Name)})

    manifest_version = assignments.get("__version__")

    if not isinstance(manifest_version, str):
        logger.debug(f"Manifest of plugin {name!r} does not declare a version number")
        return None

    depends = assignments.get("depends")

    return {
        "name": name,
        "version": manifest_version,
        "description": (ast.get_docstring(tree) or "").strip(),
        "depends": [dependency for dependency in depends if isinstance(dependency, str)]
        if isinstance(depends, list)
        else [],
    }


def read_plugin_manifest(path: Path, name: str) -> Manifest | None:
    """Read the manifest of a plugin located at the given path, without executing it.

    :param path: Path to the repository of the plugin
    :param name: Name of the plugin, in the format `organization/repository`
    :return: Manifest of the plugin, or `None` if it is not a valid odev plugin
    """
    manifest_path = path / PLUGIN_MANIFEST_FILENAME

    try:
        source = manifest_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        logger.debug(f"Could not read the manifest of plugin {name!r} at {manifest_path.as_posix()}")
        return None

    return parse_plugin_manifest(source, name)


_discovered: dict[Path, tuple[tuple[tuple[str, str, int], ...], "Discovery"]] = {}
"""Discoveries already made during this run, by plugins directory, with the state the directory was read at."""


def _directory_revision(plugins_path: Path) -> tuple[tuple[str, str, int], ...]:
    """Capture everything a discovery is derived from, to tell a stale one from a current one.

    Exactly the three things discovery reads are captured, for every link: the name of the link, which gives the
    module name; the repository it points to, which gives the plugin its identity; and the state of the manifest
    found there, which gives the version and the dependencies. Nothing else can change what a discovery would
    find, and anything that does invalidates it here, whether odev is the one that changed it or not.

    The modification time of the directory is deliberately not used on its own: it has a coarse granularity on
    some filesystems, so a link created within the same tick as the previous read would leave it untouched, and it
    says nothing at all about what the links point to.

    :param plugins_path: Path to the plugins directory holding the links
    :return: An opaque value that changes whenever a discovery of this directory would find something else
    """
    try:
        paths = sorted(plugins_path.iterdir())
    except OSError:
        return ()

    revision: list[tuple[str, str, int]] = []

    for path in paths:
        target = path.resolve()

        try:
            # A target that is gone, or whose manifest is, reads as 0 and differs from the run that found one.
            manifest_revision = (target / PLUGIN_MANIFEST_FILENAME).stat().st_mtime_ns
        except OSError:
            manifest_revision = 0

        revision.append((path.name, target.as_posix(), manifest_revision))

    return tuple(revision)


def installed_plugins(plugins_path: Path) -> "Discovery":
    """Read the plugins directory once, reporting the plugins to load and the ones that had to be left out.

    The result is kept for as long as nothing a discovery depends on has changed: the configuration, the framework
    and the plugin command all need it, and reading the directory again would also report a broken plugin twice.
    Linking, unlinking, retargeting a link, or changing the manifest it points to discards the result on its own,
    whether odev is the one that did it or not.

    :param plugins_path: Path to the plugins directory holding the links
    :return: The plugins to load and the ones that were skipped
    """
    revision = _directory_revision(plugins_path)
    cached = _discovered.get(plugins_path)

    if cached is None or cached[0] != revision:
        discovery = _discover(plugins_path)

        for plugin in discovery.skipped:
            logger.warning(f"Ignoring plugin {plugin.name!r}: {plugin.reason}")

        cached = (revision, discovery)
        _discovered[plugins_path] = cached

    return cached[1]


def forget_plugins() -> None:
    """Discard the discovered plugins so the next discovery reads the plugins directory again.

    Discovery notices on its own everything it is derived from, so this is a safety net rather than the mechanism:
    it is there for a caller that would rather not depend on that, and for tests swapping a directory wholesale.
    """
    _discovered.clear()


def _discover(plugins_path: Path) -> "Discovery":
    """Read every link under the plugins directory and work out what can be loaded from it.

    :param plugins_path: Path to the plugins directory holding the links
    :return: The plugins to load and the ones that were skipped
    """
    plugins, unreadable = _linked_plugins(plugins_path)
    usable, incomplete = _drop_missing_dependencies(plugins)
    ordered, cyclic = _dependency_order(usable)

    return Discovery(
        ordered,
        sorted(unreadable + incomplete + cyclic, key=lambda plugin: plugin.name),
        [plugins[name] for name in sorted(plugins)],
    )


def _linked_plugins(plugins_path: Path) -> tuple[dict[str, Plugin], list["SkippedPlugin"]]:
    """Read every link under the plugins directory, setting aside the ones that are not usable plugins.

    :param plugins_path: Path to the plugins directory holding the links
    :return: The plugins found mapped by name, and the links that could not be read
    """
    plugins: dict[str, Plugin] = {}
    skipped: list[SkippedPlugin] = []

    for path in _linked_paths(plugins_path):
        target = path.resolve()
        name = plugin_identity(target)

        if not target.is_dir():
            skipped.append(SkippedPlugin(name, path, f"{path.as_posix()} does not point to a directory anymore"))
            continue

        manifest = read_plugin_manifest(target, name)

        if manifest is None:
            skipped.append(
                SkippedPlugin(
                    name,
                    path,
                    f"{target.as_posix()} does not expose a readable {PLUGIN_MANIFEST_FILENAME} "
                    "declaring a '__version__'",
                )
            )
            continue

        plugins[name] = Plugin(name, path, manifest)

    return plugins, skipped


def _linked_paths(plugins_path: Path) -> list[Path]:
    """List every link under the plugins directory, whether it points to a usable plugin or not.

    :param plugins_path: Path to the plugins directory holding the links
    :return: The candidate links, sorted by name
    """
    if not plugins_path.is_dir():
        return []

    # Dotted and underscored entries are never valid python modules, so they cannot be plugins and are left to
    # whoever put them there.
    return sorted(path for path in plugins_path.iterdir() if not path.name.startswith((".", "_")))


def _drop_missing_dependencies(plugins: Mapping[str, Plugin]) -> tuple[dict[str, Plugin], list["SkippedPlugin"]]:
    """Set aside the plugins depending on a plugin that is not installed, and those depending on them in turn.

    :param plugins: The plugins to filter, mapped by name
    :return: The plugins whose dependencies are all installed, and the ones that were set aside
    """
    usable = dict(plugins)
    skipped: list[SkippedPlugin] = []

    # Dropping a plugin can leave the plugins depending on it without a dependency in turn, so sweep again until a
    # pass drops nothing.
    while True:
        dropped = {
            name: sorted(dep for dep in plugin.manifest["depends"] if dep not in usable)
            for name, plugin in usable.items()
        }
        dropped = {name: missing for name, missing in dropped.items() if missing}

        if not dropped:
            break

        for name, missing in dropped.items():
            plugin = usable.pop(name)
            skipped.append(
                SkippedPlugin(
                    name,
                    plugin.path,
                    f"it depends on {', '.join(missing)}, which {'is' if len(missing) == 1 else 'are'} not installed",
                )
            )

    return usable, skipped


def _dependency_order(plugins: Mapping[str, Plugin]) -> tuple[list[Plugin], list["SkippedPlugin"]]:
    """Order plugins so that each one comes after the plugins it depends on.

    The order is what reproduces the patches a plugin applies to another, so a plugin taking part in a dependency
    cycle has no position it could be imported at and is set aside.

    :param plugins: The plugins to order, mapped by name
    :return: The ordered plugins, and the ones caught in a cycle
    """
    remaining = {
        name: {dep for dep in plugin.manifest["depends"] if dep in plugins} for name, plugin in plugins.items()
    }
    ordered: list[Plugin] = []
    resolved: set[str] = set()

    while remaining:
        generation = sorted(name for name, dependencies in remaining.items() if dependencies <= resolved)

        if not generation:
            break

        ordered.extend(plugins[name] for name in generation)
        resolved.update(generation)

        for name in generation:
            del remaining[name]

    cyclic = [
        SkippedPlugin(
            name,
            plugins[name].path,
            f"it is caught in a circular dependency with {', '.join(sorted(dependencies))}",
        )
        for name, dependencies in sorted(remaining.items())
    ]

    return ordered, cyclic


def plugin_link(discovery: "Discovery", name: str) -> Path | None:
    """Find the link recording a plugin as installed, whatever name that link was given.

    The link is usually named after the repository it points to, but nothing enforces it: a link made by hand can
    carry any name, and its plugin would be unreachable if it were only ever looked up at the conventional path.

    :param discovery: The last reading of the plugins directory
    :param name: Name of the plugin, in the format `organization/repository`
    :return: Path to the link, or `None` if no link records that plugin
    """
    for plugin in [*discovery.installed, *discovery.skipped]:
        if plugin.name == name:
            return plugin.path

    return None


def plugins_requiring(plugins: Iterable[Plugin], name: str) -> list[str]:
    """List the plugins depending on the given plugin, directly or through another plugin.

    :param plugins: The plugins to look through
    :param name: Name of the plugin whose dependents are looked up
    :return: Names of the dependent plugins, sorted
    """
    depends = {plugin.name: set(plugin.manifest["depends"]) for plugin in plugins}
    depends.pop(name, None)
    removed = {name}
    dependents: list[str] = []

    while found := sorted(plugin for plugin, dependencies in depends.items() if dependencies & removed):
        dependents += found
        removed |= set(found)

        for plugin in found:
            del depends[plugin]

    return dependents
