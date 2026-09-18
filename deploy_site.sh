#!/usr/bin/env bash
# Publish site/ to the gh-pages branch.
#
# gh-pages carries only the contents of site/ at its root (docs/site_data_sources.md).
# This mirrors site/ onto that branch through a temporary worktree, so whatever
# branch you have checked out is never touched.
#
#   bash deploy_site.sh              commit and push
#   bash deploy_site.sh --dry-run    show what would change, push nothing
#
# If a previous run was interrupted, stale locks can block git. Clear them with:
#   git worktree prune
#   rm -f .git/index.lock .git/refs/heads/gh-pages.lock
set -euo pipefail

cd "$(dirname "$0")"
DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1

git worktree prune
WT=".git/ghp-deploy"
rm -rf "$WT"

cleanup() { git worktree remove --force "$WT" >/dev/null 2>&1 || rm -rf "$WT"; git worktree prune; }
trap cleanup EXIT

git fetch origin gh-pages
git worktree add --force --detach "$WT" origin/gh-pages

# Mirror site/ into the branch root, keeping .git and .nojekyll.
rsync -a --delete --exclude '.git' --exclude '.nojekyll' site/ "$WT"/
touch "$WT/.nojekyll"

git -C "$WT" add -A
if git -C "$WT" diff --cached --quiet; then
  echo "gh-pages already matches site/; nothing to publish."
  exit 0
fi

echo "--- changes that would be published ---"
git -C "$WT" diff --cached --stat

if [ "$DRY" = 1 ]; then
  echo "(dry run: nothing committed or pushed)"
  exit 0
fi

git -C "$WT" commit -m "site: publish current site/"
git -C "$WT" push origin HEAD:gh-pages
echo "published. GitHub Pages usually refreshes within a minute."
