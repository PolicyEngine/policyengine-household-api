#!/bin/bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

FRAGMENTS=$(find changelog.d -type f ! -name ".gitkeep" | wc -l | tr -d ' ')

if [ "$FRAGMENTS" -eq 0 ]; then
  echo "::error::No changelog fragment found in changelog.d/"
  echo "Add one with: echo 'Description.' > changelog.d/\$(git branch --show-current).<type>.md"
  echo "Types: added, changed, fixed, removed, breaking"
  exit 1
fi

echo "Found $FRAGMENTS changelog fragment(s)."
