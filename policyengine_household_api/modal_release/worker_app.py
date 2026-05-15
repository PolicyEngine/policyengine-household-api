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
        "enable_memory_snapshot": True,
    }
    if environment == "main":
        options["min_containers"] = 3
        options["buffer_containers"] = 2
        options["scaledown_window"] = 600
    return options


@app.cls(**worker_function_options())
class HouseholdWorker:
    """Worker class for handling household API requests.

    Uses a Modal class with ``@modal.enter(snap=True)`` so the heavy Flask
    app import runs at memory-snapshot creation time. Subsequent container
    starts restore from the snapshot in seconds rather than re-running the
    full policyengine country-package import chain on every cold start.
    """

    @modal.enter(snap=True)
    def load_flask_app(self) -> None:
        # Importing `policyengine_household_api.api` runs
        # `initialize_analytics_db_if_enabled` at module level, which opens a
        # Cloud SQL connection in environments where analytics is enabled.
        # That connection needs GOOGLE_APPLICATION_CREDENTIALS, set by
        # `configure_google_credentials()`. Configure credentials first so the
        # snapshot-time import can succeed even before any request method runs.
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
        # Also re-runs `configure_google_credentials()` in case Modal did
        # not preserve `/tmp` across snapshots and the credentials file is
        # missing on the restored filesystem.
        # See: https://modal.com/docs/guide/memory-snapshot
        configure_google_credentials()

        from policyengine_household_api.data import analytics_setup

        if not analytics_setup.is_analytics_enabled():
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
        return dispatch_to_flask_app(self.flask_app, payload)
