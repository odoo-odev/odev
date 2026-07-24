# Working in the Odev repository

Here's some information that may be helpful while working on an Odev PR:

-   **Setup** - This short guide describes how to get this app running on your local machine.
-   **Styling** - How code is kept coherent and readable for all involved developers.
-   **Reusable modules** - Generic methods and classes are defined separately and imported when necessary.
-   **Pre-Commit** - Pre-Commit hooks are used to ensure consistency and correctness of the codebase. They run
    automatically in your PR but it is recommended to run them locally too.
-   **Tests** - Tests are used to ensure changes do not break existing features. Tests run automatically in your PR, and
    sometimes it's also helpful to run them locally.
-   **Upgrades** - Sometimes a change in the code requires modifying the app' structure. Migration scripts are used to
    ensure this remains transparent to the end user.

## IDE setup

The repository ships configuration files so that most of the development tooling works out of the box:

-   **`pyrightconfig.json`** - Configuration for [basedpyright](https://docs.basedpyright.com) (or pyright), providing
    type checking, completion and go-to-definition. Recommended VSCode extensions: `detachhead.basedpyright`,
    `charliermarsh.ruff` and `editorconfig.editorconfig`.
-   **`.basedpyright/baseline.json`** - Pre-existing type errors are
    [baselined](https://docs.basedpyright.com/latest/benefits-over-pyright/baseline/) so only new errors are reported.
    After fixing baselined errors, refresh the file with `basedpyright --writebaseline`.
-   **`.editorconfig`** - Basic editor settings (indentation, line length, line endings) applied by most editors.
-   **`.ruff.toml`** - Linting and formatting rules, enforced by pre-commit and the CI.
-   **`.vscode/settings.json`** - Editor settings shared by all contributors. Everything else under `.vscode/` is
    gitignored and machine-local.
-   **`odev/plugins` symlink** - Created by `install-dev.sh` (and gitignored), it points to `~/.config/odev/plugins` so
    static analyzers resolve `odev.plugins.*` imports across installed plugins. `install.sh` does not create it: end
    users never need it and Odev does not use it at runtime, it is excluded from `ruff`, `coverage` and `basedpyright`
    and hidden from the VSCode explorer by `.vscode/settings.json`.

> [!IMPORTANT]
>
> Never browse or edit plugin sources through `odev/plugins`. Editors resolve that path back to the plugin's real
> location, outside of this repository, which reports every `odev` and `odev.plugins` import as unresolved. Open plugin
> sources from their own repository instead - go-to-definition already takes you there.

When working on Odev and its plugins together, clone the plugin repositories as siblings of your Odev checkout and use
a VSCode [multi-root workspace](https://code.visualstudio.com/docs/editing/workspaces/multi-root-workspaces) (kept in
the gitignored `.vscode/` directory) with one folder per repository. Plugin repositories ship a `pyrightconfig.json`
declaring `"extraPaths": [".", "../odev"]`, which resolves the `odev` package from within a plugin; the relative
`../odev` only works if the checkouts are siblings.
