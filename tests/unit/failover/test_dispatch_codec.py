from policyengine_household_common.dispatch_codec import (
    decode_dispatch_request,
    decode_dispatch_response,
    encode_dispatch_request,
    encode_dispatch_response,
)
from policyengine_household_common.routing_metadata import (
    MODAL_ROUTING_PAYLOAD_KEY,
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
