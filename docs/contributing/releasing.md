# Releasing

Odev and its plugins are published through two branches:

-   `beta` collects the changes of the next release. Every pull request targets `beta`.
-   `main` tracks the latest release. It only ever moves by being **fast-forwarded** to `beta`.

Both branches are protected and users follow either of them as their release channel, so their history is never
rewritten: after a release `main` and `beta` point to the very same commit. This is taken care of by the
[`release`](../../.github/workflows/release.yml) workflow, nobody pushes to those branches by hand.

## What the workflow does

| When                                 | What happens                                                                         |
| ------------------------------------ | ------------------------------------------------------------------------------------ |
| A pull request is opened on `main`   | It is retargeted to `beta`, unless it carries the `hotfix` label.                    |
| A pull request is merged in `beta`   | The version is bumped on `beta` and the release pull request is created or updated.  |
| `/release` is commented on that PR   | `main` is fast-forwarded to `beta`, tagged `vX.Y.Z` and a GitHub release is created. |
| `main` moves, `beta` is deleted, daily | `beta` is created if missing and brought back on top of `main` if needed.          |

### Versioning

The version is derived from the prefixes of the commits waiting on `beta`, see [versioning](./versioning.md). It is
written by a single `[REL] odev: bump the version to X.Y.Z` commit, pushed to `beta` by the release bot. A second one
only appears when a later change calls for a higher version during the same cycle, for instance when an improvement
lands after a fix.

### Releasing

The release pull request (`beta` → `main`, titled `[REL] odev: release X.Y.Z`) is always open while changes are
waiting. Its description is the changelog of the release.

1. Review and approve the release pull request, wait for its checks to pass.
2. Comment `/release` on it (or run the `release` workflow manually with the _release_ option).

> [!IMPORTANT]
>
> Never use the merge button on the release pull request. Squashing or rebasing rewrites the commits, `main` then
> diverges from `beta` and `beta` has to be rewritten, which breaks the checkout of every user of the beta channel.

Releasing requires write access to the repository, an approved pull request without requested changes and successful
checks; the bot answers with the reason when it refuses to release.

### Repairing `beta`

If `main` receives commits that are not on `beta` (a `hotfix` pull request, a release merged with the merge button),
the changes of `beta` that `main` does not contain yet are replayed on top of `main` and `beta` is force-pushed. If they
cannot be replayed without conflict, the workflow fails and opens an issue: `beta` then needs to be rebased by hand by
an administrator. Prefer landing urgent fixes on `beta` and releasing right away over using the `hotfix` label.

## Setup

The branch ruleset forbids creating, deleting and pushing to `main` and `beta`, and the token of GitHub Actions cannot
be exempted from it. The workflow therefore acts as a GitHub App. This is done once by an administrator of the
organization:

1. Create a GitHub App owned by the organization with the repository permissions _Contents_, _Pull requests_ and
   _Issues_ set to _Read and write_. No webhook is needed.
2. Install the app on the repositories of odev and its plugins.
3. Add the app to the bypass list of the ruleset protecting `main` and `beta`, with the mode _Always allow_.
4. Store the identifier and a private key of the app as organization secrets named `ODEV_RELEASE_APP_ID` and
   `ODEV_RELEASE_APP_PRIVATE_KEY`.

Until the secrets exist the workflow does nothing but report that it is disabled.

The workflow reacts to comments, schedules and pull requests from forks using the files of the default branch: changes
made to the release workflows are effective once they are released to `main`.

## Plugins

The logic lives in the reusable workflow [`release-flow`](../../.github/workflows/release-flow.yml). A plugin enables
it with a single file, `.github/workflows/release.yml`:

```yaml
name: release

on:
  push:
    branches: [main, beta]
  delete:
  issue_comment:
    types: [created]
  pull_request_target:
    types: [opened, reopened, edited]
    branches: [main]
  schedule:
    - cron: '17 4 * * *'
  workflow_dispatch:
    inputs:
      release:
        description: Release beta to main (requires an approved release pull request)
        type: boolean
        default: false

permissions:
  contents: read
  pull-requests: write

jobs:
  release-flow:
    if: >-
      (github.event_name != 'delete' || github.event.ref == 'beta')
      && (
        github.event_name != 'issue_comment'
        || (github.event.issue.pull_request && startsWith(github.event.comment.body, '/release'))
      )
    uses: odoo-odev/odev/.github/workflows/release-flow.yml@main
    with:
      package: odev-plugin-example
      version-file: __manifest__.py
      release: ${{ inputs.release || false }}
    secrets:
      app_id: ${{ secrets.ODEV_RELEASE_APP_ID }}
      app_private_key: ${{ secrets.ODEV_RELEASE_APP_PRIVATE_KEY }}
```
