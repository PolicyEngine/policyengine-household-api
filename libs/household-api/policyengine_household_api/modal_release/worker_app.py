from __future__ import annotations

import os
from typing import Any

import modal
from policyengine_observability import operation
from policyengine_observability import set_attribute

from policyengine_household_api.modal_release.google_credentials import (
    configure_google_credentials,
)
from policyengine_household_api.modal_release.images import (
    household_api_secret,
    household_api_worker_image,
)
from policyengine_household_common.release_manifest import build_app_name
from policyengine_household_common.worker_dispatch import (
    dispatch_to_flask_app,
)
from policyengine_household_common.observability.flask import (
    configure_process_observability,
)


WORKER_APP_NAME = os.getenv(
    "HOUSEHOLD_MODAL_WORKER_APP_NAME", build_app_name()
)

app = modal.App(WORKER_APP_NAME)


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
        "enable_memory_snapshot": True,
        # Hard cap on autoscale. Without this Modal is bounded only by the
        # workspace quota, so a runaway traffic spike (or a buggy partner
        # client) could scale to hundreds of containers and rack up cost.
        # 100 covers any realistic partner burst we expect today (peak 100
        # concurrent x 5 inputs = 500 in-flight) while keeping accidents
        # bounded.
        "max_containers": 100,
    }
    if environment == "main":
        options["min_containers"] = 3
        options["buffer_containers"] = 2
        options["scaledown_window"] = 600
    return options


def worker_concurrency_options() -> dict[str, int]:
    # Each container processes up to 5 requests in parallel (`max_inputs`).
    # With ~3s of CPU per request on a 1-core container, 5-way sharing gives
    # ~15s wall-time per request when fully saturated. Multiplies effective
    # warm-pool capacity 5x with no additional container cost.
    #
    # `target_inputs=4` is the autoscaler's steady-state goal: keep average
    # utilisation at 80% so each container retains one free slot to absorb
    # single-request spikes without waiting on a cold start. Containers still
    # burst up to `max_inputs=5` under load before queueing.
    return {"max_inputs": 5, "target_inputs": 4}


@app.cls(**worker_function_options())
@modal.concurrent(**worker_concurrency_options())
class HouseholdWorker:
    """Worker class for handling household API requests.

    Uses a Modal class with ``@modal.enter(snap=True)`` so the heavy Flask
    app import runs at memory-snapshot creation time. Subsequent container
    starts restore from the snapshot in seconds rather than re-running the
    full policyengine country-package import chain on every cold start.
    """

    @modal.enter(snap=True)
    def load_flask_app(self) -> None:
        configure_process_observability(
            platform="modal",
            service_role="modal_worker",
            modal_app_name=WORKER_APP_NAME,
            modal_function_name="HouseholdWorker.handle_household_request",
        )
        # Configure credentials before importing the Flask app so any request
        # path that lazily initializes Google-backed clients after snapshot
        # restore has a usable credentials file.
        configure_google_credentials()

        from policyengine_household_api.api import app as flask_app

        self.flask_app = flask_app

    @modal.enter(snap=False)
    def reset_post_snapshot_state(self) -> None:
        # Runs on every container start AFTER snapshot restore. Memory
        # snapshots preserve Python object state but not live network
        # connections; the SQLAlchemy pool and the Cloud SQL Connector
        # captured in the snapshot hold sockets that closed at snapshot
        # time. Reset them so the first request opens fresh connections.
        #
        # Also force-recreate the Google credentials file: Modal preserves
        # env vars across snapshot restore, but /tmp is not guaranteed to
        # be preserved. Without popping the env var first,
        # configure_google_credentials() would short-circuit on the
        # surviving GOOGLE_APPLICATION_CREDENTIALS and leave it pointing
        # at a missing file, breaking analytics DB reconnects.
        # See: https://modal.com/docs/guide/memory-snapshot
        os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
        configure_google_credentials()

        from policyengine_household_api.data import analytics_setup

        if (
            not analytics_setup.is_analytics_enabled()
            or "sqlalchemy" not in self.flask_app.extensions
        ):
            return

        analytics_setup.cleanup()

        try:
            with self.flask_app.app_context():
                analytics_setup.db.engine.dispose()
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning(
                "Failed to dispose analytics DB engine after snapshot "
                "restore; subsequent queries may reconnect lazily: %s",
                exc,
            )

    @modal.method()
    def handle_household_request(
        self, payload: dict[str, Any]
    ) -> dict[str, Any]:
        with operation(
            "modal_worker_dispatch",
            flavor="modal_worker",
            platform="modal",
            runtime_role="modal_worker",
            modal_app_name=WORKER_APP_NAME,
            modal_function_name="HouseholdWorker.handle_household_request",
        ):
            set_attribute("method", str(payload.get("method") or "GET"))
            set_attribute("path", str(payload.get("path") or ""))
            result = dispatch_to_flask_app(self.flask_app, payload)
            set_attribute("status_code", str(result.get("status_code")))
            return result
