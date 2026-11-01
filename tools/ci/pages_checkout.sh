#!/usr/bin/env bash
[ -n "${BASH_VERSION:-}" ] || exec bash "$0" "$@"   # started from sh or zsh: run under bash
# Check out the gh-pages branch into DIR as a git worktree (created as an empty orphan branch on first use).
#   tools/ci/pages_checkout.sh site
set -euo pipefail
dir="${1:?usage: pages_checkout.sh DIR}"
if git ls-remote --exit-code --heads origin gh-pages >/dev/null 2>&1; then
  git fetch --depth 1 origin gh-pages
  git worktree add -B gh-pages "$dir" FETCH_HEAD
else
  git worktree add --orphan -b gh-pages "$dir"
fi
python3 "$(dirname "$0")/../publish/site.py" init "$dir"
