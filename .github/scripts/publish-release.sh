#!/usr/bin/env bash

# Fast-forward the release branch to the released revision, tag it and publish the release.
#
# Expects the changelog written by `check-release.sh` in `$RUNNER_TEMP/changelog.md`.
#
# Environment:
#   RELEASE_BRANCH      branch tracking the latest release
#   PRERELEASE_BRANCH   branch collecting the changes of the next release
#   PACKAGE             name of the released package
#   NUMBER              number of the release pull request
#   REVISION            commit to release
#   VERSION             version to release
#   GH_TOKEN            token allowed to bypass the protection of the release branch

set -euo pipefail

# Pushing the very same commits keeps both branches identical: the pull request is marked as merged
# and the pre-release branch remains untouched, ready for the next changes.
git push origin "$REVISION:refs/heads/$RELEASE_BRANCH"
git push origin "$REVISION:refs/tags/v$VERSION"

gh release create "v$VERSION" --verify-tag --title "$PACKAGE $VERSION" \
  --notes-file "$RUNNER_TEMP/changelog.md"
gh pr comment "$NUMBER" --body \
  ":rocket: Released as [v$VERSION]($GITHUB_SERVER_URL/$GITHUB_REPOSITORY/releases/tag/v$VERSION)"
