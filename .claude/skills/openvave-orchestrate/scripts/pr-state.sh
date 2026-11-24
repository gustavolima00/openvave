#!/usr/bin/env bash
# Print the readiness facts for one PR:
# draft flag, mergeable, mergeStateStatus, failing or pending checks, and
# every unresolved review thread with its last commenter. Whether a reply
# actually answers a finding needs reading the thread; this only lists them.
#
# Usage: pr-state.sh <pr-number>
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "usage: $0 <pr-number>" >&2
  exit 2
fi
pr=$1
repo=$(gh repo view --json nameWithOwner -q .nameWithOwner)
owner=${repo%/*} name=${repo#*/}

gh pr view "$pr" --json number,url,isDraft,mergeable,mergeStateStatus,headRefOid,statusCheckRollup -q '
  "pr: \(.url)",
  "head: \(.headRefOid)",
  "draft: \(.isDraft)",
  "mergeable: \(.mergeable)",
  "mergeStateStatus: \(.mergeStateStatus)",
  "checks_failing: \([.statusCheckRollup[] | select((.conclusion // .state) as $c | ["FAILURE","ERROR","CANCELLED","TIMED_OUT","ACTION_REQUIRED"] | index($c)) | (.name // .context)] | join(", "))",
  "checks_pending: \([.statusCheckRollup[] | select((.status // "") as $s | ["QUEUED","IN_PROGRESS","PENDING","WAITING"] | index($s)) | (.name // .context)] | join(", "))"
'

gh api graphql -F owner="$owner" -F name="$name" -F pr="$pr" -f query='
  query($owner: String!, $name: String!, $pr: Int!) {
    repository(owner: $owner, name: $name) {
      pullRequest(number: $pr) {
        reviewThreads(first: 100) {
          nodes { isResolved path comments(last: 1) { totalCount nodes { url author { login } } } }
        }
      }
    }
  }' -q '
  [.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved | not)] as $open
  | "unresolved_threads: \($open | length)",
    ($open[] | "  - \(.path) (\(.comments.totalCount) comments, last by \(.comments.nodes[0].author.login)): \(.comments.nodes[0].url)")
'
