from __future__ import annotations

import os

import modal

from policyengine_household_api.modal_release.images import (
    household_api_canary_image,
)


CANARY_APP_NAME = os.getenv(
    "HOUSEHOLD_MODAL_CANARY_APP_NAME",
    "policyengine-household-api-canary",
)
CANARY_SERVICE_NAME = "household-api-modal-canary"

app = modal.App(CANARY_APP_NAME)


def canary_function_options() -> dict[str, object]:
    return {
        "image": household_api_canary_image(),
        "timeout": 10,
        "scaledown_window": 300,
    }


def canary_payload() -> dict[str, object]:
    return {"ok": True, "service": CANARY_SERVICE_NAME}


@app.function(**canary_function_options())
def ping() -> dict[str, object]:
    return canary_payload()
