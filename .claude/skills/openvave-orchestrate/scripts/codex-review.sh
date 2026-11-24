#!/usr/bin/env bash
# Run Codex's native code reviewer (`codex review`) on a branch's changes
# against a base, non-interactively and read-only.
#
# Usage: codex-review.sh <worktree> <base-ref> <out-dir>
#   base-ref: what the PR merges into, normally origin/main (fetch first).
#
# Codex uses the model from ~/.codex/config.toml at reasoning effort "high"
# (override with CODEX_REVIEW_EFFORT=low|medium|high|xhigh). `codex review`
# runs in Codex's read-only sandbox and publishes nothing: the caller posts
# the result on the PR.
#
# stdout of `codex review` is the final review only: a summary paragraph and
# "Full review comments:" with one "- [P0..P3] <title> — <abs path>:<lines>"
# item per finding (no list when there are no findings). The session log
# goes to stderr.
#
# Prints `review=<file>`, `log=<file>`, `head=<sha>`, `findings=<n>` and
# `p0_p1=<n>`; exits with Codex's status.
set -euo pipefail

if [ "$#" -ne 3 ]; then
  echo "usage: $0 <worktree> <base-ref> <out-dir>" >&2
  exit 2
fi
worktree=$1 base=$2 out=$3
effort=${CODEX_REVIEW_EFFORT:-high}

cd "$worktree"
git rev-parse --verify --quiet "$base^{commit}" > /dev/null || {
  echo "error: unknown base ref '$base' (run git fetch origin?)" >&2
  exit 2
}
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "error: uncommitted changes in $worktree; commit before reviewing so the review matches a SHA" >&2
  exit 2
fi
head=$(git rev-parse HEAD)

mkdir -p "$out"
stamp=$(date +%Y%m%d-%H%M%S)
review="$out/codex-review-${head:0:7}-$stamp.md"
log="$out/codex-review-${head:0:7}-$stamp.log"

set +e
codex review --base "$base" -c model_reasoning_effort="$effort" \
  < /dev/null > "$review" 2> "$log"
status=$?
set -e

if grep -q 'model_not_found' "$log"; then
  echo "error: Codex rejected the model; the CLI is probably too old (codex --version: $(codex --version)). Run: brew upgrade codex" >&2
fi
findings=$(grep -cE '^- \[P[0-3]\]' "$review" || true)
p0_p1=$(grep -cE '^- \[P[01]\]' "$review" || true)
echo "review=$review"
echo "log=$log"
echo "head=$head"
echo "findings=$findings"
echo "p0_p1=$p0_p1"
exit "$status"
