"""Search, enable and disable plugins to add new features and commands."""

import textwrap
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from git import InvalidGitRepositoryError, NoSuchPathError
from github import GithubException, RateLimitExceededException
from github.Repository import Repository

from odev.common import args, progress, string
from odev.common.commands import Command
from odev.common.connectors import GitConnector, GithubConnector
from odev.common.connectors.git import GITHUB_DOMAIN, GITHUB_SEARCH_DEFAULT_LIMIT
from odev.common.console import TableHeader
from odev.common.errors import ConnectorError
from odev.common.logging import logging
from odev.common.odev import (
    PLUGIN_MANIFEST_FILENAME,
    Manifest,
    parse_plugin_manifest,
    plugin_module_name,
)


logger = logging.getLogger(__name__)


SEARCH_KEYWORDS = "odev plugin"
"""Keywords a repository must match to be considered a candidate odev plugin.
The `odev` keyword alone is far too noisy to be usable, as it collides with unrelated repositories.
"""

SEARCH_QUALIFIERS = "in:name,description,topics"
"""Fields the search keywords are matched against on GitHub."""

EXCLUDED_REPOSITORIES = frozenset({"odoo-odev/odev-plugin-template"})
"""Repositories exposing a plugin manifest but that cannot be installed, such as the template repository
used as a starting point to create new plugins.
"""

STATE_ENABLED = "enabled"
"""The plugin is linked under the plugins directory and loaded by the framework."""

STATE_SHADOWED = "shadowed"
"""The plugin is enabled in the configuration but another plugin already uses its module name."""

STATE_MISSING = "missing"
"""The plugin is enabled in the configuration but is not linked under the plugins directory."""

STATE_DISABLED = "disabled"
"""The plugin is available locally but is not enabled."""

STATE_NOT_DOWNLOADED = "not downloaded"
"""The plugin exists on GitHub but is not available locally."""

STATE_STYLES: Mapping[str, str] = {
    STATE_ENABLED: "color.green",
    STATE_SHADOWED: "color.yellow",
    STATE_MISSING: "color.red",
    STATE_DISABLED: "color.black",
    STATE_NOT_DOWNLOADED: "color.black",
}
"""Style used to render each possible state of a plugin."""

STATE_ORDER: tuple[str, ...] = (
    STATE_ENABLED,
    STATE_SHADOWED,
    STATE_MISSING,
    STATE_DISABLED,
    STATE_NOT_DOWNLOADED,
)
"""Order in which plugins are sorted in tables, most relevant states first."""

DESCRIPTION_MAX_WIDTH = 60
"""Maximum width of a plugin description before it gets truncated in tables."""

NAME_MIN_WIDTH = 32
"""Minimum width reserved for plugin names in tables, as they are needed to enable a plugin."""


@dataclass(frozen=True)
class PluginInfo:
    """Everything known about a plugin, whether it is available locally or only on GitHub."""

    name: str
    """Name of the plugin, in the format `organization/repository`."""

    state: str
    """Current state of the plugin, one of the `STATE_*` constants."""

    version: str = ""
    """Version number declared in the manifest of the plugin."""

    branch: str = ""
    """Branch currently checked out in the local clone of the plugin."""

    path: Path | None = None
    """Path to the local clone of the plugin, if it exists."""

    depends: list[str] = field(default_factory=list)
    """Other plugins this one depends on."""

    description: str = ""
    """Description of the plugin, taken from the docstring of its manifest."""

    shadowed_by: str = ""
    """Plugin already using the module name of this one, preventing it from being loaded."""

    stars: int | None = None
    """Number of stars of the repository, `None` if it was not looked up on GitHub."""

    archived: bool = False
    """Whether the repository is archived and no longer maintained."""


class PluginCommand(Command):
    """Search, enable and disable plugins to add new features and commands."""

    _name = "plugin"
    _aliases = ["plugins"]
    _exclusive_arguments = [("enable", "disable", "show", "search", "list")]

    enable = args.Flag(aliases=["-e", "--enable"], description="Download and enable an inactive plugin.")
    disable = args.Flag(aliases=["-d", "--disable"], description="Disable an active plugin.")
    show = args.Flag(
        aliases=["-s", "--show"],
        description="Show the state of a plugin and its description if available.",
    )
    search = args.Flag(
        aliases=["-S", "--search"],
        description="""Search GitHub for plugins matching the given terms.
        Only repositories exposing a valid plugin manifest are listed.
        """,
    )
    action_list = args.Flag(
        name="list",
        aliases=["-l", "--list"],
        description="List the plugins available locally, whether they are enabled or not.",
    )
    limit = args.Integer(
        aliases=["-n", "--limit"],
        default=GITHUB_SEARCH_DEFAULT_LIMIT,
        description="Maximum number of repositories to inspect when searching for plugins.",
    )
    branch = args.String(
        aliases=["-b", "--branch"],
        description="""Git revision (branch, tag or commit) to check out when enabling a plugin.
        Takes precedence over the release channel set in the 'update.release' configuration key.
        Only the plugin being enabled is affected, its dependencies keep following the release channel.
        """,
    )
    plugin = args.String(
        description="""Plugin to enable or disable, must be a git repository hosted on GitHub.
        Use format <organization>/<repository>.
        If `--show` is used and no plugin is provided, show the state of all enabled plugins.
        If `--search` is used, this is the term to search for; quote it to search for multiple terms.
        """,
        nargs="?",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.__local_plugins: list[PluginInfo] | None = None
        """Cached list of the plugins known locally."""

        if not self.args.plugin and not (self.args.show or self.args.search or self.args.list):
            raise self.error("Missing argument: plugin")

        if self.args.branch and not self.args.enable:
            raise self.error("Argument --branch can only be used together with --enable")

    def run(self):
        """Search, list, enable or disable plugins."""
        if self.args.search:
            self.search_plugins()

        if self.args.list:
            self.list_plugins()

        if self.args.show:
            self.show_plugins()

        if self.args.enable:
            self.odev.install_plugin(
                self.__resolve_plugin_name(self.args.plugin),
                revision=self.args.branch or None,
            )

        if self.args.disable:
            self.odev.uninstall_plugin(self.__resolve_plugin_name(self.args.plugin))

    # --- Searching plugins on GitHub ------------------------------------------

    def search_plugins(self) -> None:
        """Search GitHub for odev plugins and display the results in a table."""
        terms = self.args.plugin or ""
        query = " ".join(part for part in (SEARCH_KEYWORDS, terms, SEARCH_QUALIFIERS) if part)
        states = {plugin.name: plugin.state for plugin in self._discover_plugins()}
        github = GithubConnector()
        rows: list[list[Any]] = []

        with progress.spinner(f"Searching GitHub for plugins matching {SEARCH_KEYWORDS} {terms}".strip()) as status:
            for repository in self.__search_repositories(github, query):
                status.update(f"Inspecting repository {repository.full_name!r}")
                manifest = self.__remote_manifest(github, repository)

                if manifest is None:
                    continue

                state = states.get(repository.full_name, STATE_NOT_DOWNLOADED)
                rows.append(
                    [
                        string.link(repository.full_name, repository.html_url),
                        manifest["version"],
                        str(repository.stargazers_count),
                        string.stylize(state, STATE_STYLES[state]),
                        self.__shorten(manifest["description"] or repository.description or ""),
                    ]
                )

        if not rows:
            raise self.error(f"No odev plugin found matching {terms!r}" if terms else "No odev plugin found on GitHub")

        headers = [
            TableHeader("Plugin", min_width=NAME_MIN_WIDTH, style="color.purple"),
            TableHeader("Version", align="right", style="repr.version"),
            TableHeader("Stars", align="right"),
            TableHeader("State"),
            TableHeader("Description"),
        ]

        self.print()
        self.table(headers, rows, title=f"Plugins matching {terms!r}" if terms else "Plugins")
        self.console.clear_line()

        logger.info("Run 'odev plugin --enable <organization>/<repository>' to install one of these plugins")

    def __search_repositories(self, github: GithubConnector, query: str) -> list[Repository]:
        """Query the GitHub search API and discard the repositories that cannot be plugins.

        :param github: Connector to the GitHub API.
        :param query: The search query, using the GitHub search syntax.
        :return: The candidate repositories to inspect.
        """
        try:
            repositories = github.search_repositories(query, limit=self.args.limit)
        except RateLimitExceededException as error:
            raise self.error("GitHub API rate limit exceeded, please try again in a few minutes") from error
        except GithubException as error:
            raise self.error(f"Failed to search for plugins on GitHub: {error}") from error

        return [
            repository
            for repository in repositories
            if not repository.archived and repository.full_name not in EXCLUDED_REPOSITORIES
        ]

    def __remote_manifest(self, github: GithubConnector, repository: Repository) -> Manifest | None:
        """Fetch and parse the manifest of a remote repository to check whether it is an odev plugin.

        :param github: Connector to the GitHub API.
        :param repository: The remote repository to inspect.
        :return: The manifest of the plugin, or `None` if the repository is not an odev plugin.
        """
        source = github.get_repository_file(repository, PLUGIN_MANIFEST_FILENAME)

        if source is None:
            return None

        return parse_plugin_manifest(source, repository.full_name)

    # --- Listing local plugins ------------------------------------------------

    def list_plugins(self) -> None:
        """List the plugins known locally and display them in a table."""
        plugins = self._discover_plugins()

        if not plugins:
            raise self.error("No plugin found locally")

        headers = [
            TableHeader("Plugin", min_width=NAME_MIN_WIDTH, style="color.purple"),
            TableHeader("Version", align="right", style="repr.version"),
            TableHeader("Branch", style="color.cyan"),
            TableHeader("State"),
            TableHeader("Depends"),
        ]
        rows = [
            [
                string.link(plugin.name, f"https://{GITHUB_DOMAIN}/{plugin.name}"),
                plugin.version,
                plugin.branch,
                string.stylize(plugin.state, STATE_STYLES[plugin.state]),
                ", ".join(dependency.split("/")[-1] for dependency in plugin.depends),
            ]
            for plugin in plugins
        ]

        self.print()
        self.table(headers, rows, title="Plugins")
        self.console.clear_line()

        if shadowed := [plugin for plugin in plugins if plugin.state == STATE_SHADOWED]:
            logger.warning(
                "The following plugins are enabled but cannot be loaded as another plugin already uses their "
                "module name:\n"
                + string.join_bullet([f"{plugin.name} (shadowed by {plugin.shadowed_by})" for plugin in shadowed])
            )

    # --- Showing a single plugin ----------------------------------------------

    def show_plugins(self) -> None:
        """Show detailed information about one plugin, or about all the plugins available locally."""
        if self.args.plugin:
            self.__show_plugin_info(self.__resolve_plugin_name(self.args.plugin))
            return

        for plugin in self._discover_plugins():
            self.__show_plugin_info(plugin.name)
            self.console.print()

    def __show_plugin_info(self, name: str) -> None:
        """Show the state of a plugin and its description if available.

        :param name: The name of the plugin, in the format `organization/repository`.
        """
        plugin = self.__plugin_info(name)

        if plugin is None:
            logger.info(
                f"Plugin {name!r} is {string.stylize(STATE_NOT_DOWNLOADED, STATE_STYLES[STATE_NOT_DOWNLOADED])}"
            )

            if "/" not in name:
                logger.info("Use the full name of the plugin as '<organization>/<repository>' to look it up on GitHub")

            return

        fields = [
            ("Version", string.stylize(plugin.version, "repr.version") if plugin.version else ""),
            ("Branch", string.stylize(plugin.branch, "color.cyan") if plugin.branch else ""),
            ("Stars", "" if plugin.stars is None else str(plugin.stars)),
            ("Path", plugin.path.as_posix() if plugin.path is not None else ""),
            ("Depends", ", ".join(plugin.depends)),
            ("URL", f"https://{GITHUB_DOMAIN}/{plugin.name}"),
        ]
        width = max(len(label) for label, value in fields if value) + 1
        details = [f"Plugin {plugin.name!r} is {string.stylize(plugin.state, STATE_STYLES[plugin.state])}"]
        details.extend(
            f"{string.stylize(f'{label}:'.ljust(width), 'color.black')} {value}" for label, value in fields if value
        )
        logger.info("\n".join(details))

        if plugin.description:
            self.console.print()
            self.console.print(string.indent(plugin.description, 4).rstrip("\n"))

        self.__warn_plugin_unusable(plugin)

    def __warn_plugin_unusable(self, plugin: PluginInfo) -> None:
        """Warn about the reasons a plugin cannot be loaded or installed, and tell how to install it otherwise.

        :param plugin: The plugin the information of which is being displayed.
        """
        if plugin.state == STATE_SHADOWED:
            logger.warning(f"Plugin {plugin.name!r} is shadowed by {plugin.shadowed_by!r} and cannot be loaded")

        if plugin.archived:
            logger.warning(f"Repository {plugin.name!r} is archived and is not maintained anymore")

        if plugin.name in EXCLUDED_REPOSITORIES:
            logger.warning(
                f"Repository {plugin.name!r} is a template used to create new plugins and cannot be installed"
            )
        elif plugin.state == STATE_NOT_DOWNLOADED:
            logger.info(f"Run 'odev plugin --enable {plugin.name}' to install this plugin")

    def __plugin_info(self, name: str) -> PluginInfo | None:
        """Gather everything known about a plugin, completing local information with GitHub when needed.

        Plugins available locally are never looked up on GitHub, so this stays offline for the common case.

        :param name: The name of the plugin, in the format `organization/repository`.
        :return: The plugin, or `None` if nothing is known about it.
        """
        plugin = next((known for known in self._discover_plugins() if known.name == name), None)

        if (plugin is not None and plugin.version) or "/" not in name:
            return plugin

        remote = self.__fetch_remote_plugin(name)

        if remote is None:
            return plugin

        if plugin is None:
            return remote

        return replace(
            plugin,
            version=remote.version,
            branch=plugin.branch or remote.branch,
            depends=remote.depends,
            description=remote.description,
            stars=remote.stars,
            archived=remote.archived,
        )

    def __fetch_remote_plugin(self, name: str) -> PluginInfo | None:
        """Fetch the details of a plugin from GitHub, without cloning it.

        Failing to reach GitHub is not an error: the plugin is then only described by what is known locally.

        :param name: The name of the plugin, in the format `organization/repository`.
        :return: The plugin as published on GitHub, or `None` if it could not be fetched.
        """
        try:
            with progress.spinner(f"Fetching plugin {name!r} from GitHub"):
                github = GithubConnector()
                repository = github.get_repository(name)

                if repository is None:
                    return None

                manifest = self.__remote_manifest(github, repository)
        except (ConnectorError, GithubException) as error:
            logger.debug(f"Could not fetch plugin {name!r} from GitHub: {error}")
            return None

        if manifest is None:
            logger.debug(f"Repository {name!r} does not expose a valid plugin manifest")
            return None

        return PluginInfo(
            name=repository.full_name,
            state=STATE_NOT_DOWNLOADED,
            version=manifest["version"],
            branch=repository.default_branch,
            depends=list(manifest["depends"]),
            description=manifest["description"] or repository.description or "",
            stars=repository.stargazers_count,
            archived=repository.archived,
        )

    # --- Discovering local plugins --------------------------------------------

    def _discover_plugins(self) -> list[PluginInfo]:
        """List all the plugins known locally, whether they are enabled, disabled or broken.

        :return: The plugins known locally, sorted by state then by name.
        """
        if self.__local_plugins is None:
            plugins = self.__discover_enabled()
            plugins.update(self.__discover_configured(plugins))
            plugins.update(self.__discover_downloaded(plugins))

            self.__local_plugins = sorted(
                plugins.values(),
                key=lambda plugin: (STATE_ORDER.index(plugin.state), plugin.name),
            )

        return self.__local_plugins

    def __discover_enabled(self) -> dict[str, PluginInfo]:
        """List the plugins linked under the plugins directory and loaded by the framework.

        :return: The enabled plugins, mapped by name.
        """
        plugins: dict[str, PluginInfo] = {}

        for plugin in self.odev.plugins:
            resolved_path = plugin.path.resolve()

            if plugin.path.name.startswith((".", "_")) or not resolved_path.is_dir():
                continue

            plugins[plugin.name] = PluginInfo(
                name=plugin.name,
                state=STATE_ENABLED,
                version=plugin.manifest["version"],
                branch=self.__repository_branch(resolved_path),
                path=resolved_path,
                depends=list(plugin.manifest["depends"]),
                description=(plugin.manifest["description"] or "").strip(),
            )

        return plugins

    def __discover_configured(self, enabled: Mapping[str, PluginInfo]) -> dict[str, PluginInfo]:
        """List the plugins enabled in the configuration that the framework could not load.

        :param enabled: The plugins already discovered as enabled, mapped by name.
        :return: The plugins whose link is either missing or taken by another plugin, mapped by name.
        """
        modules = {plugin_module_name(name): name for name in enabled}
        plugins: dict[str, PluginInfo] = {}

        for name in self.config.plugins.enabled:
            if name in enabled:
                continue

            shadowed_by = modules.get(plugin_module_name(name), "")
            plugins[name] = self.__build_plugin(
                name,
                self.config.paths.repositories / name,
                STATE_SHADOWED if shadowed_by else STATE_MISSING,
                shadowed_by=shadowed_by,
            )

        return plugins

    def __discover_downloaded(self, known: Mapping[str, PluginInfo]) -> dict[str, PluginInfo]:
        """List the plugins cloned locally but neither enabled nor referenced in the configuration.

        Repositories that cannot be installed are left out so they are never advertised as available, but a plugin
        already enabled is always reported, whatever its repository.

        :param known: The plugins already discovered, mapped by name.
        :return: The plugins available locally but not enabled, mapped by name.
        """
        repositories_path = self.config.paths.repositories
        plugins: dict[str, PluginInfo] = {}

        if not repositories_path.is_dir():
            return plugins

        for manifest_path in sorted(repositories_path.glob(f"*/*/{PLUGIN_MANIFEST_FILENAME}")):
            path = manifest_path.parent
            name = f"{path.parent.name}/{path.name}"

            if name in known or name in plugins or name in EXCLUDED_REPOSITORIES:
                continue

            manifest = self.__read_manifest(path, name)

            if manifest is None:
                continue

            plugins[name] = self.__build_plugin(name, path, STATE_DISABLED, manifest=manifest)

        return plugins

    def __build_plugin(
        self,
        name: str,
        path: Path,
        state: str,
        manifest: Manifest | None = None,
        shadowed_by: str = "",
    ) -> PluginInfo:
        """Build the representation of a plugin that is not loaded by the framework.

        :param name: The name of the plugin, in the format `organization/repository`.
        :param path: The expected path to the local clone of the plugin.
        :param state: The state of the plugin, one of the `STATE_*` constants.
        :param manifest: The already parsed manifest of the plugin, read from `path` if omitted.
        :param shadowed_by: The plugin already using the module name of this one, if any.
        :return: The plugin as known locally.
        """
        manifest = manifest or self.__read_manifest(path, name)

        return PluginInfo(
            name=name,
            state=state,
            version=manifest["version"] if manifest else "",
            branch=self.__repository_branch(path),
            path=path if path.is_dir() else None,
            depends=list(manifest["depends"]) if manifest else [],
            description=manifest["description"] if manifest else "",
            shadowed_by=shadowed_by,
        )

    def __read_manifest(self, path: Path, name: str) -> Manifest | None:
        """Read the manifest of a plugin located at the given path, without executing it.

        :param path: The path to the local clone of the plugin.
        :param name: The name of the plugin, in the format `organization/repository`.
        :return: The manifest of the plugin, or `None` if it is not a valid odev plugin.
        """
        manifest_path = path / PLUGIN_MANIFEST_FILENAME

        if not manifest_path.is_file():
            return None

        try:
            source = manifest_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            logger.debug(f"Could not read the manifest of plugin {name!r} at {manifest_path.as_posix()}")
            return None

        return parse_plugin_manifest(source, name)

    def __repository_branch(self, path: Path) -> str:
        """Return the branch currently checked out in the local clone of a plugin.

        :param path: The path to the local clone of the plugin.
        :return: The name of the active branch, empty if the path is not a git repository.
        """
        if not (path / ".git").exists():
            return ""

        try:
            return GitConnector(path.as_posix()).branch or ""
        except (ConnectorError, InvalidGitRepositoryError, NoSuchPathError, ValueError):
            logger.debug(f"Could not determine the branch of the repository at {path.as_posix()}")
            return ""

    def __resolve_plugin_name(self, name: str) -> str:
        """Resolve a plugin name given on the command line to its full `organization/repository` name.

        :param name: The name of the plugin, either fully qualified or the name of its repository only.
        :return: The fully qualified name of the plugin, unchanged if it could not be resolved.
        """
        if "/" in name:
            return name

        candidates = [plugin.name for plugin in self._discover_plugins() if plugin.name.split("/")[-1] == name]

        if len(candidates) > 1:
            raise self.error(f"Plugin name {name!r} is ambiguous, use one of:\n{string.join_bullet(candidates)}")

        return candidates[0] if candidates else name

    def __shorten(self, description: str) -> str:
        """Collapse a description to a single line fitting the width of a table column.

        :param description: The description to shorten.
        :return: The shortened description.
        """
        return textwrap.shorten(description, DESCRIPTION_MAX_WIDTH, placeholder="...")
