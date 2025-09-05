# Plugins

Odev relies on plugins to add new features or extend existing ones. Those plugins are hosted in external GitHub
repositories and can be enabled and disabled directly within Odev.

To enable a plugin, run `odev plugin --enable <organization>/<repository>`.

## Table of contents

-   [Plugins](#plugins)
    -   [Table of contents](#table-of-contents)
    -   [Creating a new plugin](#creating-a-new-plugin)
        -   [Plugin structure](#plugin-structure)
            -   [The manifest](#the-manifest)
            -   [Commands](#commands)
            -   [Commons](#commons)
        -   [Cross-module imports](#cross-module-imports)
        -   [Adding a new command](#adding-a-new-command)
        -   [Extending a command](#extending-a-command)

## Creating a new plugin

To create a new odev plugin, start by creating a new repository. You can copy a
[template repository](https://github.com/odoo-odev/odev-plugin-template) to kickstart your project.

> [!TIP]
>
> The template repository contains configuration files that can be used by linters and git hooks to format your code
> according to our standards. It is recommended to install and use `pre-commit` when working on plugins.

Update the `README.md` file copied from the template to ensure all details are correct.

### Plugin structure

An Odev plugin is structured by a manifest file and the `commands` and `common` directories:

```txt
my-plugin/
├── commands/
│   └── command.py
├── common/
│   └── feature.py
├── __manifest__.py
└── README.md
```

#### The manifest

Each plugin needs a manifest file which will describe its usage, keep track of its version and define its dependencies.

Create a new file `__manifest__.py` at the root of your plugin with the following content (copied from the template
repository). Replace the docstring by a summary of your module's features. This will be read by Odev and displayed when
required by the `odev plugin` command.

If any, add the dependencies (other plugins) of your own plugin. For example, `odoo-odev/odev-plugin-editor-vscode`
depends on the abstract plugin `odoo-odev/odev-plugin-editor-base` which is therefore required for the plugin to work:
[VScode Editor plugin's depends](https://github.com/odoo-odev/odev-plugin-editor-vscode/blob/main/__manifest__.py#L38).

```python
"""Plugin description."""

# --- Version information ------------------------------------------------------
#
# Version number breakdown: <major>.<minor>.<patch>
#
# major:  Major version number, incremented when a new major feature is added
#         when important changes are made to the framework or when backwards
#         compatibility is broken.
# minor:  Minor version number, incremented when a new minor feature is added
#         that does not break backwards compatibility. This may indicate
#         additions of new commands or new features to existing commands.
#         This number is reset to 0 when the major version number is
#         incremented.
# patch:  Patch version number, incremented when a bug is fixed or when
#         documentation is updated. May also be incremented when a new
#         migration script is added.
#         This number is reset to 0 when the minor version number is
#         incremented.
#
# Version number should be incremented once and only once per pull request
# or merged change.
# ------------------------------------------------------------------------------

__version__ = "1.0.0"

# --- Dependencies -------------------------------------------------------------
# List other odev plugins from which this current plugin depends.
# Those dependent plugins will be loaded first, allowing this one to inject
# code into existing commands to empower them.
#
# The format for listing a plugin is the same as the one expected in the plugin
# command: "<github organization>/<repository name>".
#
# All plugins depend from odev core by default.
# ------------------------------------------------------------------------------

depends = []

```

#### Commands

Python files added under `commands/` will be loaded at startup and any non-abstract class inheriting from the base
`Command` class will be loaded as a standalone command.

#### Commons

The `common` directory contains additional features and helpers that can be used by your commands. They will typically
add new connectors or extend existing helpers.

### Cross-module imports

To import features from the core Odev repository or another dependent module, you can use python imports.

> [!NOTE]
>
> Your linter might not detect `odev` and `odev.plugins`, but Odev will load correctly at runtime if the plugins are
> enabled.

> [!TIP]
>
> To import from a plugin, resolve the name of the plugin by replacing dashes `-` by underscores `_` and removing the
> organization from the plugin name. As such, to import the class `Editor` from defined in the plugin
> `odoo-odev/odev-plugin-editor-base` use `from odev.plugins.odev_plugin_editor_base.common.editor import Editor`.

```python
# Import a command class from Odev
from odev.common.commands import OdoobinCommand

# Import a custom helper from another plugin (or my own)
from odev.plugins.odev_my_plugin.common import my_helper
```

### Adding a new command

To add a brand new command, follow the same steps as in [Adding a new command](./commands.md#adding-a-new-command),
placing your file in the `commands` directory of your plugin.

### Extending a command

Sometime you'll want to extend a command instead of creating a new one. Simply import the class of the command you want
to extend and inherit from it without specifying a new name. Odev is smart enough to understand that you modified the
features of the existing command.

```python
from odev.commands.database.info import InfoCommand as BaseInfoCommand


class InfoCommand(BaseInfoCommand):

    def run(self):
        super().run()
        self.print("Mom look, I extended a command!")

```

### Adding config parameters

It is often a great choice to let users choose between different options, and your plugins should act accordingly. But
the user experience could be impacted negatively if the same question is asked again and again without a reason. To
counter this, we use configuration files that will store the values your user chose.

That configuration file is already handled for you, but you still have to define the possible values. We do that with
getters and setters in a new config's `Section` class.

Create a new file `config.py` at the root of your plugin.

```python
from odev.common.config import Section


class TestSection(Section):
    _name = "test"

    @property
    def test(self) -> str:
        """Test config parameter."""
        return self.get("test", "TEST")

    @test.setter
    def test(self, value: str):
        self.set("test", value.upper())

```

Let's break this down: the section has a `_name` and, in this example, a property. The name will be used as a container
for all the parameters in this section. You can add as many sections as you want, with the sole condition that its name
remains unique across all plugins.

To add a config parameter, add a new property in that section. The name of the property will serve as the config
parameter within the Odev framework. To fetch the information stored in the configuration file, we'll use `self.get()`
with two arguments: the key of the option in the file and and default value. The configuration file stores data as a
single-line string, and that is what `self.get()` will return, but the property can return anything of any type so don't
hesitate to transform the value before returning it.

To allow Odev writing a new value, add a setter for that same property. It can take any value of any type but must
transform it into a single-line string before passing it to `self.set()`.

From within odev, you can fetch or set a value from the configuration at any time through the config object.

```python
value = odev.config.test.test  # -> "TEST"
odev.config.test.test = "New Value"  # -> "NEW VALUE"
```
