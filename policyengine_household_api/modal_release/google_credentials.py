from __future__ import annotations

import os
from pathlib import Path


def configure_google_credentials() -> None:
    credentials_json = os.getenv("GCP_CREDENTIALS_JSON")
    if not credentials_json or os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        return

    credentials_path = Path("/tmp/policyengine-household-api-gcp.json")
    credentials_path.write_text(credentials_json)
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(credentials_path)
