# GitHub PRs

These rules apply to every developer and AI agent opening pull requests in this
repository.

## Same-repository PRs

Open PRs from branches in `PolicyEngine/policyengine-household-api`, not from
personal forks. The PR workflow uses repository secrets for the full test lane,
so same-repository branches are the reliable review path.

Before creating or sharing a PR:

1. Confirm the canonical repository is reachable:
   `gh repo view PolicyEngine/policyengine-household-api --json nameWithOwner`.
2. Open a GitHub issue for the work, or verify that an appropriate issue
   already exists.
3. Put `Fixes #ISSUE_NUMBER` as the first line of the PR description, using the
   issue number from the issue created or found in the previous step.
4. Add a Towncrier changelog fragment under `changelog.d/` using the issue
   number or a clear slug and the appropriate configured type, for example
   `changelog.d/ISSUE_NUMBER.added.md`.
5. Run repository-wide local checks where practical, not only checks scoped to
   files the PR author or AI agent changed. At minimum, run the configured
   whole-repository lint/format check with `make format-check`; do not
   substitute targeted commands like `ruff check path/to/changed_file.py`.
   Also run `make test`, and, when Auth0 test configuration is available,
   `make test-with-auth`.
6. Push the current branch to the canonical repository:
   `git push origin HEAD`.
7. Create the PR as a draft from that same repository:
   `gh pr create --draft --repo PolicyEngine/policyengine-household-api --head "$(git branch --show-current)" --base main`.
8. Verify the PR is draft and the head repository is canonical:
   `gh pr view <PR> --repo PolicyEngine/policyengine-household-api --json isDraft,headRepositoryOwner,headRepository`.
9. Before sharing the PR, verify CI has been checked:
   `gh pr checks <PR> --repo PolicyEngine/policyengine-household-api`.

If you cannot push to the canonical repository, stop and ask for access. Do not
create a fork PR as a fallback. If you accidentally create one, close it and
replace it with a same-repository draft PR.

## PR Title

Do not add `[codex]`, `[claude]`, `[copilot]`, or other agent labels to PR
titles. Use a plain descriptive title.
