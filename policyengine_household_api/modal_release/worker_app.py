from __future__ import annotations

import os
from typing import Any

import modal

from policyengine_household_api.modal_release.google_credentials import (
    configure_google_credentials,
)
from policyengine_household_api.modal_release.images import (
    household_api_image,
    household_api_secret,
)
from policyengine_household_api.modal_release.manifest import build_app_name
from policyengine_household_api.modal_release.worker_dispatch import (
    dispatch_to_flask_app,
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
def handle_household_request(payload: dict[str, Any]) -> dict[str, Any]:
    configure_google_credentials()
    from policyengine_household_api.api import app as flask_app

    return dispatch_to_flask_app(flask_app, payload)
