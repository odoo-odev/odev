#!/usr/bin/env bash

# Bump the version on the pre-release branch according to the changes waiting for a release.
#
# Run from a full clone of the repository checked out on the pre-release branch. Outputs the `version` to release
# and writes its changelog to `$RUNNER_TEMP/changelog.md`; outputs nothing when there is nothing to release.
#
# Environment:
#   RELEASE_BRANCH      branch tracking the latest release
#   PRERELEASE_BRANCH   branch collecting the changes of the next release
#   PACKAGE             name of the released package
#   VERSION_FILE        path to the file assigning `__version__`
#   APP_SLUG            slug of the GitHub App, used as the author of the bump commit

set -euo pipefail

tooling=$(dirname "$0")

release="origin/$RELEASE_BRANCH"

if ! git merge-base --is-ancestor "$release" HEAD; then
  echo "::warning::'$PRERELEASE_BRANCH' does not contain '$RELEASE_BRANCH', waiting for the branches to be synced"
  exit 0
fi

version=$(python3 "$tooling/release.py" next-version --base "$release" --head HEAD --version-file "$VERSION_FILE")

if [ -z "$version" ]; then
  echo "::notice::Nothing to release"
  exit 0
fi

python3 "$tooling/release.py" changelog --base "$release" --head HEAD > "$RUNNER_TEMP/changelog.md"
python3 "$tooling/release.py" bump --version-file "$VERSION_FILE" --version "$version"

if ! git diff --quiet -- "$VERSION_FILE"; then
  git config user.name "${APP_SLUG}[bot]"
  git config user.email "${APP_SLUG}[bot]@users.noreply.github.com"
  git commit --message "[REL] $PACKAGE: bump the version to $version" -- "$VERSION_FILE"
  git push origin "HEAD:refs/heads/$PRERELEASE_BRANCH"
  echo "::notice::Bumped the version to $version"
fi

echo "version=$version" >> "$GITHUB_OUTPUT"
