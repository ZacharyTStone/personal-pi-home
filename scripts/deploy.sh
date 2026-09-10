#!/usr/bin/env bash
#
# Pull the latest version of your fork and restart the stack.
#
# This is what you run on the box after pushing a change from your
# laptop, and what a cron line runs if you want it automatic:
#
#     cd ~/personal-pi-home && ./scripts/deploy.sh
#
# It's deliberately boring — pull, rebuild, restart, tidy up. The one
# thing it will not do is touch hub/data/, which is the state that stops
# your hub from re-notifying you about everything it has already sent.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "→ Fetching…"
git fetch --quiet origin

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
LOCAL="$(git rev-parse HEAD)"
REMOTE="$(git rev-parse "origin/${BRANCH}")"

if [ "$LOCAL" = "$REMOTE" ]; then
  echo "→ Already up to date ($BRANCH @ ${LOCAL:0:7}). Nothing to do."
  exit 0
fi

# Refuse to clobber edits made directly on the box. Config changes belong
# in git so the next rebuild doesn't quietly undo them.
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "✗ You have uncommitted changes on the box:" >&2
  git status --short >&2
  echo >&2
  echo "  Commit and push them, or 'git stash' them, then run this again." >&2
  exit 1
fi

echo "→ Updating $BRANCH: ${LOCAL:0:7} → ${REMOTE:0:7}"
git merge --ff-only "origin/${BRANCH}"

echo "→ Rebuilding and restarting…"
docker compose up -d --build

# Old images add up fast on a 32 GB card.
echo "→ Pruning old images…"
docker image prune -f >/dev/null

echo "→ Done. Status:"
docker compose ps
echo
echo "Logs:      docker compose logs -f hub"
echo "Dashboard: http://$(hostname -I 2>/dev/null | awk '{print $1}'):8090"
