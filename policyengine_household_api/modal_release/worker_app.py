from __future__ import annotations

import os
from pathlib import Path

import modal

from policyengine_household_api.modal_release.images import (
    household_api_image,
    household_api_secret,
)
from policyengine_household_api.modal_release.manifest import build_app_name
from policyengine_household_api.modal_release.worker_guard import (
    install_gateway_guard,
)


app = modal.App(
    os.getenv("HOUSEHOLD_MODAL_WORKER_APP_NAME", build_app_name()),
    image=household_api_image(),
)


@app.function(
    secrets=[household_api_secret()],
    timeout=180,
    scaledown_window=300,
)
@modal.wsgi_app()
def web_app():
    _configure_google_credentials()
    from policyengine_household_api.api import app as flask_app

    install_gateway_guard(flask_app)
    return flask_app


def _configure_google_credentials() -> None:
    credentials_json = os.getenv("GCP_CREDENTIALS_JSON")
    if not credentials_json or os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        return

    credentials_path = Path("/tmp/policyengine-household-api-gcp.json")
    credentials_path.write_text(credentials_json)
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(credentials_path)
