# Versioning

When making changes, the version number of Odev must be incremented so that upgrades can be run.

Increment parts of the version number in [`odev/_version.py`](../../odev/_version.py) according to the following
requirements:

**Version number breakdown:** `<major>.<minor>.<patch>`

-   `major`: Major version number, incremented when a new major feature is added when important changes are made to the
    framework or when backwards compatibility is broken.
-   `minor`: Minor version number, incremented when a new minor feature is added that does not break backwards
    compatibility. This may indicate additions of new commands or new features to existing commands. This number is
    reset to 0 when the major version number is incremented.
-   `patch`: Patch version number, incremented when a bug is fixed or when documentation is updated. May also be
    incremented when a new migration script is added. This number is reset to 0 when the minor version number is
    incremented.

**Version number should be incremented once and only once per pull request or merged change.**