from __future__ import annotations

import logging
import os

import modal
from policyengine_observability import ObservabilityConfig
from policyengine_observability import ObservabilityRuntime
from policyengine_observability import operation
from policyengine_observability import set_attribute
from policyengine_observability import set_observability_runtime

from policyengine_household_api.modal_release.images import (
    household_api_canary_image,
    household_api_secret,
)


CANARY_APP_NAME = os.getenv(
    "HOUSEHOLD_MODAL_CANARY_APP_NAME",
    "policyengine-household-api-canary",
)
CANARY_SERVICE_NAME = "household-api-modal-canary"

app = modal.App(CANARY_APP_NAME)
_observability_runtime: ObservabilityRuntime | None = None


def _configure_canary_process_observability() -> None:
    os.environ.setdefault("OBSERVABILITY_PLATFORM", "modal")
    os.environ.setdefault("OBSERVABILITY_SERVICE_ROLE", "modal_canary")
    os.environ.setdefault("OBSERVABILITY_RUNTIME_ROLE", "modal_canary")
    os.environ.setdefault("OBSERVABILITY_MODAL_APP_NAME", CANARY_APP_NAME)
    os.environ.setdefault("OBSERVABILITY_MODAL_FUNCTION_NAME", "ping")


def init_canary_observability() -> None:
    global _observability_runtime

    if _observability_runtime is not None:
        return
    try:
        _configure_canary_process_observability()
        runtime = ObservabilityRuntime(
            ObservabilityConfig.from_env(
                service_name="policyengine-household-api",
                service_role="modal_canary",
                span_prefix="household",
            )
        )
        runtime.configure()
        set_observability_runtime(runtime)
        _observability_runtime = runtime
    except BaseException as exc:
        logging.getLogger(__name__).warning(
            "Failed to configure Modal canary observability: %s",
            exc,
        )


def canary_function_options() -> dict[str, object]:
    return {
        "image": household_api_canary_image(),
        "secrets": [household_api_secret()],
        "timeout": 10,
        "scaledown_window": 300,
    }


def canary_payload() -> dict[str, object]:
    return {"ok": True, "service": CANARY_SERVICE_NAME}


@app.function(**canary_function_options())
def ping() -> dict[str, object]:
    init_canary_observability()
    with operation(
        "modal_canary_ping",
        flavor="modal_canary",
        platform="modal",
        runtime_role="modal_canary",
        modal_app_name=CANARY_APP_NAME,
        modal_function_name="ping",
    ):
        set_attribute("modal_app_name", CANARY_APP_NAME)
        return canary_payload()
