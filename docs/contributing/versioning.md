# Versioning

The version number of Odev is incremented with each release so that upgrades can be run.

**Do not change the version number in your pull request.** The version in
[`odev/_version.py`](../../odev/_version.py) is incremented automatically, once per release, according to the prefixes
of the commits being [released](./releasing.md):

| Commit prefix                | Incremented part |
| ---------------------------- | ---------------- |
| `[REF]`                      | `major`          |
| `[IMP]`, `[FEAT]`, `[ADD]`   | `minor`          |
| `[FIX]`, `[DOC]`, any other  | `patch`          |

The prefix of the commit merged into `beta` therefore matters: pick the one matching the following definitions.

**Version number breakdown:** `<major>.<minor>.<patch>`

-   `major`: Major version number, incremented when a new major feature is added when important changes are made to the
    framework or when backwards compatibility is broken.
-   `minor`: Minor version number, incremented when a new minor feature is added that does not break backwards
    compatibility. This may indicate additions of new commands or new features to existing commands. This number is
    reset to 0 when the major version number is incremented.
-   `patch`: Patch version number, incremented when a bug is fixed or when documentation is updated. May also be
    incremented when a new migration script is added. This number is reset to 0 when the minor version number is
    incremented.

Upgrade scripts are stored under `odev/upgrades/<version>`, named after the version in which they are released. When adding
one, use the version announced by the open release pull request, or the next patch version if there is none, and make
sure the prefix of your commit leads to a version that is at least as high.
