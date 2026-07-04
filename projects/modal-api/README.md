# modal-api

The Modal apps for the PolicyEngine Household API: the worker apps that host
the core household application, the version-routing gateway, the health-check
canary, and the release manifest CLIs (`update_manifest`, `prune_manifest`,
`rewrite_manifest`, `analytics_revision`).

Never published. Image builds export the member's locked closure with
`uv export` because Modal's `Image.uv_sync` does not support uv workspaces;
first-party packages are attached as local Python sources from the deploy
machine's `uv sync --all-packages` checkout.
