from policyengine_household_common.dispatch_codec import (
    decode_dispatch_request,
    decode_dispatch_response,
    encode_dispatch_request,
    encode_dispatch_response,
)
from policyengine_household_common.routing_metadata import (
    MODAL_ROUTING_PAYLOAD_KEY,
)
from policyengine_household_common.worker_dispatch import (
    GATEWAY_RATE_LIMITED_PAYLOAD_KEY,
)


def test_dispatch_request_round_trips_bytes_and_routing_metadata():
    payload = {
        "method": "POST",
        "path": "/us/calculate",
        "query_string": "debug=1",
        "headers": {"Content-Type": "application/json"},
        "body": b'{"household": {}}',
        MODAL_ROUTING_PAYLOAD_KEY: {
            "requested_version": "frontier",
            "resolved_channel": "frontier",
        },
    }

    decoded = decode_dispatch_request(encode_dispatch_request(payload))

    assert decoded == payload


def test_dispatch_response_round_trips_bytes_and_headers():
    result = {
        "status_code": 200,
        "body": b'{"status": "ok"}',
        "headers": [("Content-Type", "application/json")],
    }

    decoded = decode_dispatch_response(encode_dispatch_response(result))

    assert decoded == result


def test_dispatch_request_round_trips_gateway_rate_limit_marker():
    payload = {
        "method": "POST",
        "path": "/us/calculate_demo",
        "query_string": "",
        "headers": {},
        "body": b"",
        MODAL_ROUTING_PAYLOAD_KEY: None,
        GATEWAY_RATE_LIMITED_PAYLOAD_KEY: True,
    }

    decoded = decode_dispatch_request(encode_dispatch_request(payload))

    assert decoded[GATEWAY_RATE_LIMITED_PAYLOAD_KEY] is True


def test_dispatch_request_decode_ignores_non_boolean_rate_limit_marker():
    decoded = decode_dispatch_request(
        {
            "method": "POST",
            "path": "/us/calculate_demo",
            GATEWAY_RATE_LIMITED_PAYLOAD_KEY: "true",
        }
    )

    assert GATEWAY_RATE_LIMITED_PAYLOAD_KEY not in decoded
