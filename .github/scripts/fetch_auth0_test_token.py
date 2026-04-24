#!/usr/bin/env python3
"""Fetch a staging Auth0 token and export it for later workflow steps."""

from __future__ import annotations

import json
import os
import urllib.request


def main() -> int:
    url = f"https://{os.environ['AUTH0_DOMAIN']}/oauth/token"
    payload = json.dumps(
        {
            "client_id": os.environ["AUTH0_CLIENT_ID"],
            "client_secret": os.environ["AUTH0_CLIENT_SECRET"],
            "audience": os.environ["AUTH0_AUDIENCE"],
            "grant_type": "client_credentials",
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.loads(response.read().decode("utf-8"))

    token = body["access_token"]
    print(f"::add-mask::{token}")

    github_env = os.environ["GITHUB_ENV"]
    with open(github_env, "a", encoding="utf-8") as handle:
        handle.write(f"HOUSEHOLD_API_AUTH_TOKEN={token}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
