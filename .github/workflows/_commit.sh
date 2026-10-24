#!/usr/bin/env bash
# Commit data/ and site/data and push with a rebase-retry loop so concurrent collector runs never fight.
set -euo pipefail
msg="${1:-moonape: collect}"
git config user.name "moonape-bot"
git config user.email "moonape-bot@users.noreply.github.com"
git add -A data site/data
if git diff --cached --quiet; then echo "nothing to commit"; exit 0; fi
git commit -q -m "$msg"
for i in 1 2 3 4 5 6; do
  if git pull --rebase -q origin main && git push -q origin HEAD:main; then echo "pushed"; exit 0; fi
  echo "push attempt $i failed; retrying"; sleep $((RANDOM % 20 + 5))
done
echo "could not push after 6 attempts"; exit 1
