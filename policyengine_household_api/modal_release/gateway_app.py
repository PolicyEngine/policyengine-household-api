from __future__ import annotations

import os

import modal

from policyengine_household_api.modal_release.gateway import create_gateway_app
from policyengine_household_api.modal_release.images import (
    household_api_gateway_image,
    household_api_secret,
)


GATEWAY_APP_NAME = os.getenv(
    "HOUSEHOLD_MODAL_GATEWAY_APP_NAME",
    "policyengine-household-api-gateway",
)
GATEWAY_WEB_ENDPOINT_LABEL = os.getenv(
    "HOUSEHOLD_MODAL_GATEWAY_WEB_ENDPOINT_LABEL",
    "household-api-gateway",
)


def gateway_wsgi_app_options() -> dict[str, object]:
    return {"label": GATEWAY_WEB_ENDPOINT_LABEL}


app = modal.App(GATEWAY_APP_NAME)


@app.function(
    image=household_api_gateway_image(),
    secrets=[household_api_secret()],
    timeout=180,
    scaledown_window=300,
)
@modal.wsgi_app(**gateway_wsgi_app_options())
def web_app():
    return create_gateway_app()
