#!/usr/bin/env bash

# Check that the pre-release branch can be released, refusing with a comment on the release pull request otherwise.
#
# Run from a full clone of the repository checked out on the pre-release branch. Outputs the `number` of the release
# pull request, the `revision` and the `version` to release, and writes the changelog to `$RUNNER_TEMP/changelog.md`.
#
# Environment:
#   RELEASE_BRANCH      branch tracking the latest release
#   PRERELEASE_BRANCH   branch collecting the changes of the next release
#   VERSION_FILE        path to the file assigning `__version__`
#   ACTOR               user asking for the release
#   COMMENTED_NUMBER    pull request on which `/release` was commented, empty when run manually
#   GH_TOKEN            token used to read and comment the pull request

set -euo pipefail

tooling=$(dirname "$0")

release="origin/$RELEASE_BRANCH"
number=$(gh pr list --base "$RELEASE_BRANCH" --head "$PRERELEASE_BRANCH" --state open \
  --json number --jq '.[0].number // empty')

refuse() {
  echo "::error::$1"

  if [ -n "$number" ]; then
    gh pr comment "$number" --body ":x: Cannot release: $1"
  fi

  exit 1
}

if [ -z "$number" ]; then
  refuse "there is no open release pull request from '$PRERELEASE_BRANCH' to '$RELEASE_BRANCH'"
fi

if [ -n "$COMMENTED_NUMBER" ] && [ "$COMMENTED_NUMBER" != "$number" ]; then
  echo "::notice::Ignoring '/release' on #$COMMENTED_NUMBER, the release pull request is #$number"
  exit 0
fi

permission=$(gh api "repos/$GITHUB_REPOSITORY/collaborators/$ACTOR/permission" --jq '.permission')

if [ "$permission" != "admin" ] && [ "$permission" != "write" ]; then
  refuse "@$ACTOR is not allowed to release, write access to the repository is required"
fi

pull_request=$(gh pr view "$number" --json headRefOid,reviewDecision,latestReviews,statusCheckRollup)
revision=$(jq --raw-output '.headRefOid' <<< "$pull_request")

if [ "$revision" != "$(git rev-parse HEAD)" ]; then
  refuse "the pull request is not in sync with '$PRERELEASE_BRANCH' yet, try again in a moment"
fi

if ! git merge-base --is-ancestor "$release" "$revision"; then
  refuse "'$RELEASE_BRANCH' cannot be fast-forwarded to '$PRERELEASE_BRANCH', the branches diverged"
fi

approved=$(jq --raw-output '
  (.reviewDecision == "APPROVED" or .reviewDecision == "" or .reviewDecision == null)
  and ([.latestReviews[] | select(.state == "APPROVED")] | length > 0)
  and ([.latestReviews[] | select(.state == "CHANGES_REQUESTED")] | length == 0)
' <<< "$pull_request")

if [ "$approved" != "true" ]; then
  refuse "the pull request is not approved"
fi

unsuccessful=$(jq --raw-output '
  [
    .statusCheckRollup[]
    | (if (.conclusion // "") != "" then .conclusion else (.state // "PENDING") end)
    | select(. != "SUCCESS" and . != "SKIPPED" and . != "NEUTRAL")
  ] | length
' <<< "$pull_request")

if [ "$unsuccessful" != "0" ]; then
  refuse "$unsuccessful check(s) did not pass or are still running on $revision"
fi

version=$(python3 "$tooling/release.py" next-version --base "$release" --head HEAD --version-file "$VERSION_FILE")

if [ -z "$version" ]; then
  refuse "there is nothing to release"
fi

python3 "$tooling/release.py" bump --version-file "$VERSION_FILE" --version "$version"

if ! git diff --quiet -- "$VERSION_FILE"; then
  refuse "the version was not bumped to $version on '$PRERELEASE_BRANCH' yet, try again in a moment"
fi

python3 "$tooling/release.py" changelog --base "$release" --head HEAD > "$RUNNER_TEMP/changelog.md"

{
  echo "number=$number"
  echo "revision=$revision"
  echo "version=$version"
} >> "$GITHUB_OUTPUT"
