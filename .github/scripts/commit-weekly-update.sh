#!/bin/bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

UPDATES_SUMMARY="${UPDATES_SUMMARY:?UPDATES_SUMMARY must be set}"
BRANCH_NAME="bot/weekly-us-update"

git config user.name "github-actions[bot]"
git config user.email "github-actions[bot]@users.noreply.github.com"
git switch -C "$BRANCH_NAME"

shopt -s nullglob
FRAGMENTS=(changelog.d/*.md)
if [ "${#FRAGMENTS[@]}" -eq 0 ]; then
  echo "Expected at least one changelog fragment in changelog.d/"
  exit 1
fi

git add pyproject.toml uv.lock "${FRAGMENTS[@]}"
git commit -m "Update policyengine-us (${UPDATES_SUMMARY})"
git push -f origin "$BRANCH_NAME"
