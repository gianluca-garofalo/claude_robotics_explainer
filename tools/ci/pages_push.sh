#!/usr/bin/env bash
[ -n "${BASH_VERSION:-}" ] || exec bash "$0" "$@"   # started from sh or zsh: run under bash
# Commit everything in the gh-pages worktree DIR and push it (retries after a concurrent update).
#   tools/ci/pages_push.sh site "message"
set -euo pipefail
dir="${1:?usage: pages_push.sh DIR MESSAGE}"; msg="${2:?message}"
cd "$dir"
git add -A
if git diff --cached --quiet; then echo "pages: nothing to commit"; exit 0; fi
git -c user.name="github-actions[bot]" -c user.email="41898282+github-actions[bot]@users.noreply.github.com" \
  commit -q -m "$msg"
for attempt in 1 2 3; do
  if git push origin HEAD:gh-pages; then exit 0; fi
  echo "pages: push rejected (attempt $attempt), rebasing on the remote branch"
  git fetch --depth 20 origin gh-pages && git rebase FETCH_HEAD
done
echo "pages: could not push" >&2
exit 1
