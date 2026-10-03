#!/usr/bin/env bash

# Create the release pull request, or update its title and description.
#
# Expects the changelog written by `bump-version.sh` in `$RUNNER_TEMP/changelog.md`.
#
# Environment:
#   RELEASE_BRANCH      branch tracking the latest release
#   PRERELEASE_BRANCH   branch collecting the changes of the next release
#   PACKAGE             name of the released package
#   VERSION             version to release
#   GH_TOKEN            token used to create or edit the pull request

set -euo pipefail

title="[REL] $PACKAGE: release $VERSION"

{
  echo "> [!IMPORTANT]"
  echo "> Do **not** merge this pull request with the merge button: it rewrites the commits and makes"
  echo "> \`$PRERELEASE_BRANCH\` diverge from \`$RELEASE_BRANCH\`. Once it is approved and its checks pass,"
  echo "> comment \`/release\` to fast-forward \`$RELEASE_BRANCH\`, tag \`v$VERSION\` and publish the release."
  echo
  echo "## $PACKAGE $VERSION"
  echo
  cat "$RUNNER_TEMP/changelog.md"
} > "$RUNNER_TEMP/body.md"

number=$(gh pr list --base "$RELEASE_BRANCH" --head "$PRERELEASE_BRANCH" --state open \
  --json number --jq '.[0].number // empty')

if [ -z "$number" ]; then
  gh pr create --base "$RELEASE_BRANCH" --head "$PRERELEASE_BRANCH" --title "$title" \
    --body-file "$RUNNER_TEMP/body.md"
else
  gh pr edit "$number" --title "$title" --body-file "$RUNNER_TEMP/body.md"
fi
