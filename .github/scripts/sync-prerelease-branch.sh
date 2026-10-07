#!/usr/bin/env bash

# Make sure the pre-release branch exists and contains the release branch.
#
# Run from a full clone of the repository, with a token allowed to bypass the protection of both branches.
#
# Environment:
#   RELEASE_BRANCH      branch tracking the latest release
#   PRERELEASE_BRANCH   branch collecting the changes of the next release
#   APP_SLUG            slug of the GitHub App, used as the author of replayed commits
#   GH_TOKEN            token used to open an issue when the branch cannot be repaired

set -euo pipefail

git config user.name "${APP_SLUG}[bot]"
git config user.email "${APP_SLUG}[bot]@users.noreply.github.com"

release="origin/$RELEASE_BRANCH"
prerelease="origin/$PRERELEASE_BRANCH"

if ! git ls-remote --exit-code --heads origin "$PRERELEASE_BRANCH" > /dev/null; then
  git push origin "$release:refs/heads/$PRERELEASE_BRANCH"
  echo "::notice::Created '$PRERELEASE_BRANCH' from '$RELEASE_BRANCH'"
  exit 0
fi

if git merge-base --is-ancestor "$release" "$prerelease"; then
  echo "::notice::'$PRERELEASE_BRANCH' already contains '$RELEASE_BRANCH'"
  exit 0
fi

if git merge-base --is-ancestor "$prerelease" "$release"; then
  git push origin "$release:refs/heads/$PRERELEASE_BRANCH"
  echo "::notice::Fast-forwarded '$PRERELEASE_BRANCH' to '$RELEASE_BRANCH'"
  exit 0
fi

# Both branches diverged: commits were added to the release branch without a fast-forward. Replay on
# top of the release branch the changes it does not contain yet; version bumps are computed again by
# the `prepare` job once the branch is pushed.
echo "::warning::'$PRERELEASE_BRANCH' diverged from '$RELEASE_BRANCH', rebasing it"
expected=$(git rev-parse "$prerelease")
git switch --detach "$release"

for commit in $(git rev-list --reverse --no-merges --cherry-pick --right-only "$release...$prerelease"); do
  case "$(git log -1 --format=%s "$commit")" in
    "[REL]"*) continue ;;
  esac

  if ! git cherry-pick --empty=drop "$commit"; then
    git cherry-pick --abort || true
    title="'$PRERELEASE_BRANCH' diverged from '$RELEASE_BRANCH' and needs a manual repair"

    if [ -z "$(gh issue list --state open --search "in:title $title" --json number --jq '.[].number')" ]; then
      gh issue create --title "$title" --body \
        "Commit $commit could not be replayed on top of \`$RELEASE_BRANCH\`, see $GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID."
    fi

    echo "::error::Cannot replay $commit on top of '$RELEASE_BRANCH'"
    exit 1
  fi
done

git push origin "HEAD:refs/heads/$PRERELEASE_BRANCH" \
  --force-with-lease="refs/heads/$PRERELEASE_BRANCH:$expected"
echo "::notice::Rebased '$PRERELEASE_BRANCH' on top of '$RELEASE_BRANCH'"
