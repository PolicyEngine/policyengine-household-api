from dataclasses import dataclass, field
import json

from flask import Response
from flask.testing import FlaskClient
import pytest

from policyengine_household_failover.cloud_run_gateway import (
    CircuitRegistry,
    create_gateway_app,
)


def _failover_manifest():
    return {
        "schema_version": 1,
        "environment": "testing",
        "generated_at": "2026-06-03T00:00:00+00:00",
        "channels": {
            "current": {
                "modal_app_name": "modal-current",
                "cloud_run_worker_url": "https://current.run.app",
                "package_versions": {"uk": "2.31.0", "us": "1.0.0"},
            },
            "frontier": {
                "modal_app_name": "modal-frontier",
                "cloud_run_worker_url": "https://frontier.run.app",
                "package_versions": {"uk": "2.88.18", "us": "2.0.0"},
            },
        },
    }


@dataclass
class GatewayUnderTest:
    """A gateway test client plus the requests its fake Modal backend received."""

    client: FlaskClient
    forwarded_payloads: list[dict] = field(default_factory=list)

    @property
    def forwarded_paths(self) -> list[str]:
        return [payload["path"] for payload in self.forwarded_payloads]


@pytest.fixture
def build_rate_limited_gateway():
    """Build a gateway whose backends are fakes, for rate-limit tests.

    ``client_ids_by_authorization`` maps an ``Authorization`` header value to
    the Auth0 client ID the gateway should treat as validated for it.
    """

    def build(*, rate_limit_config=None, client_ids_by_authorization=None):
        gateway = None
        client_ids = client_ids_by_authorization or {}

        def fake_modal_request(app_name, payload):
            gateway.forwarded_payloads.append(payload)
            return Response(
                json.dumps({"backend": "modal"}),
                status=200,
                mimetype="application/json",
            )

        app = create_gateway_app(
            manifest_loader=_failover_manifest,
            modal_request=fake_modal_request,
            modal_health_probe=lambda app_name: None,
            modal_canary_probe=lambda: None,
            fallback_request=lambda resolved, payload: Response(status=500),
            modal_status_checker=lambda: {},
            fallback_warmup=lambda resolved: None,
            circuit_registry=CircuitRegistry(),
            client_id_attributor=lambda authorization: client_ids.get(
                authorization
            ),
            rate_limit_config=rate_limit_config,
        )
        gateway = GatewayUnderTest(client=app.test_client())
        return gateway

    return build
