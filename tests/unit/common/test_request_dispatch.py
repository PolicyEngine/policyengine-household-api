from dataclasses import dataclass
import json
from types import SimpleNamespace

from flask import Flask, request
import pytest

from policyengine_household_common import gateway
from policyengine_household_common.gateway import (
    RequestVersionError,
    build_worker_request,
    country_and_endpoint,
    extract_requested_version,
    response_from_worker_result,
)
from policyengine_observability import (
    OBSERVABILITY_INTERNAL_DISPATCH_HEADER,
    REQUEST_ID_HEADER,
    TRACEPARENT_HEADER,
)


@dataclass(frozen=True)
class StubRoute:
    requested_version: str
    channel: str


def test_extract_requested_version_removes_version_from_object_body():
    body, version = extract_requested_version(
        b'{"version":"frontier","household":{}}'
    )

    assert version == "frontier"
    assert json.loads(body) == {"household": {}}


@pytest.mark.parametrize(
    "body",
    [b'["frontier"]', b'"frontier"', b"123", b"null"],
)
def test_extract_requested_version_preserves_non_object_json(body):
    rewritten, version = extract_requested_version(body)

    assert version == "current"
    assert rewritten == body


def test_extract_requested_version_rejects_non_string_version():
    with pytest.raises(RequestVersionError, match="must be a string"):
        extract_requested_version(b'{"version":{"channel":"frontier"}}')


def test_country_and_endpoint_identifies_supported_country_route():
    assert country_and_endpoint("/us/calculate") == ("us", "calculate")
    assert country_and_endpoint("/specification") == (None, None)
    assert country_and_endpoint("/zz/calculate") == (None, None)


def test_build_worker_request_uses_explicit_http_request(monkeypatch):
    app = Flask(__name__)
    monkeypatch.setattr(
        gateway,
        "current_context",
        lambda: SimpleNamespace(request_id="request-123"),
    )
    monkeypatch.setattr(
        gateway,
        "traceparent_header",
        lambda: "00-trace-parent",
    )

    with app.test_request_context(
        "/us/calculate?mode=test",
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Host": "public.example",
            "X-Test-Header": "forwarded",
        },
        data=b'{"household":{}}',
    ):
        payload = build_worker_request(
            request,
            path="us/calculate",
            body=request.get_data(),
            route=StubRoute(
                requested_version="frontier",
                channel="frontier",
            ),
        )

    assert payload == {
        "method": "POST",
        "path": "us/calculate",
        "query_string": "mode=test",
        "headers": {
            "Content-Type": "application/json",
            "X-Test-Header": "forwarded",
            REQUEST_ID_HEADER: "request-123",
            OBSERVABILITY_INTERNAL_DISPATCH_HEADER: "1",
            TRACEPARENT_HEADER: "00-trace-parent",
        },
        "body": b'{"household":{}}',
        "modal_routing": {
            "requested_version": "frontier",
            "resolved_channel": "frontier",
        },
    }


def test_response_from_worker_result_builds_flask_response():
    response = response_from_worker_result(
        {
            "status_code": 202,
            "body": "accepted",
            "headers": [("X-Worker", "modal")],
        }
    )

    assert response.status_code == 202
    assert response.get_data() == b"accepted"
    assert response.headers["X-Worker"] == "modal"
