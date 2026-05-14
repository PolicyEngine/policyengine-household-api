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
GATEWAY_CUSTOM_DOMAIN = "household.api.policyengine.org"


def gateway_custom_domains(
    *,
    modal_environment: str | None = None,
    custom_domains: str | None = None,
) -> tuple[str, ...]:
    if custom_domains is None:
        custom_domains = os.getenv("HOUSEHOLD_MODAL_GATEWAY_CUSTOM_DOMAINS")

    if custom_domains is not None:
        return tuple(
            domain.strip()
            for domain in custom_domains.split(",")
            if domain.strip()
        )

    environment = modal_environment or os.getenv("MODAL_ENVIRONMENT", "main")
    if environment == "main":
        return (GATEWAY_CUSTOM_DOMAIN,)

    return ()


GATEWAY_CUSTOM_DOMAINS = gateway_custom_domains()


def gateway_wsgi_app_options() -> dict[str, object]:
    options: dict[str, object] = {"label": GATEWAY_WEB_ENDPOINT_LABEL}
    if GATEWAY_CUSTOM_DOMAINS:
        options["custom_domains"] = GATEWAY_CUSTOM_DOMAINS
    return options


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
