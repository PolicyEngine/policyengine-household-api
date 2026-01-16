#!/bin/bash
#
# Create or update a PR for the weekly policyengine-us update.
#
# This script reads pr_summary.md and creates/updates a PR with the
# formatted body.
#
# Usage: ./create_pr.sh
#
# Environment variables:
#   GH_TOKEN - GitHub token for authentication (required)
#
set -e

BRANCH_NAME="bot/weekly-us-update"
PR_TITLE="Weekly policyengine-us update"

# Build PR body with summary
if [ ! -f "pr_summary.md" ]; then
    echo "Error: pr_summary.md not found"
    exit 1
fi

PR_SUMMARY=$(cat pr_summary.md)

PR_BODY="## Summary

Automated weekly update of policyengine-us.

Related to #1178

## Version Updates

${PR_SUMMARY}

---
Generated automatically by GitHub Actions"

# Check if PR already exists
EXISTING_PR=$(gh pr list --head "$BRANCH_NAME" --json number --jq '.[0].number' 2>/dev/null || echo "")

if [ -n "$EXISTING_PR" ]; then
    echo "PR #$EXISTING_PR already exists, updating it"
    gh pr edit "$EXISTING_PR" --body "$PR_BODY"
else
    echo "Creating new PR"
    gh pr create \
        --title "$PR_TITLE" \
        --body "$PR_BODY"
fi
