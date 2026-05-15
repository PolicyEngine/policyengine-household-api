from __future__ import annotations

import os
from typing import Any

import modal

from policyengine_household_api.modal_release.google_credentials import (
    configure_google_credentials,
)
from policyengine_household_api.modal_release.images import (
    household_api_secret,
    household_api_worker_image,
)
from policyengine_household_api.modal_release.manifest import build_app_name
from policyengine_household_api.modal_release.worker_dispatch import (
    dispatch_to_flask_app,
)


app = modal.App(
    os.getenv("HOUSEHOLD_MODAL_WORKER_APP_NAME", build_app_name()),
)


def worker_modal_environment(
    modal_environment: str | None = None,
) -> str:
    environment = (
        modal_environment
        if modal_environment is not None
        else os.getenv("MODAL_ENVIRONMENT")
    )
    if not environment:
        raise RuntimeError("MODAL_ENVIRONMENT must be set for Modal workers")
    return environment


def worker_function_options(
    modal_environment: str | None = None,
) -> dict[str, Any]:
    environment = worker_modal_environment(modal_environment)
    options: dict[str, Any] = {
        "image": household_api_worker_image(),
        "secrets": [household_api_secret()],
        "timeout": 180,
        "scaledown_window": 300,
    }
    if environment == "main":
        options["min_containers"] = 3
        options["buffer_containers"] = 2
        options["scaledown_window"] = 600
    return options


@app.function(**worker_function_options())
def handle_household_request(payload: dict[str, Any]) -> dict[str, Any]:
    configure_google_credentials()
    from policyengine_household_api.api import app as flask_app

    return dispatch_to_flask_app(flask_app, payload)
