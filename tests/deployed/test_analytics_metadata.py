from datetime import datetime, timedelta, timezone
from time import sleep
from typing import Any
from urllib.parse import urlencode
from uuid import UUID

import pytest


TOP_LEVEL_ANALYTICS_KEYS = {
    "status",
    "message",
    "start_time",
    "end_time",
    "requested_version",
    "resolved_channel",
    "unique",
    "requests",
}
REQUEST_ANALYTICS_KEYS = {
    "request_uuid",
    "created_at",
    "api_version",
    "country_id",
    "model_version",
    "requested_version",
    "resolved_channel",
    "endpoint",
    "method",
    "response_status_code",
    "distinct_variable_count",
    "unsupported_variable_count",
    "deprecated_allowlisted_variable_count",
    "variables",
}
VARIABLE_ANALYTICS_KEYS = {
    "variable_name",
    "entity_type",
    "source",
    "period_granularity",
    "entity_count",
    "period_count",
    "occurrence_count",
    "availability_status",
    "variable_name_truncated",
}
EXPECTED_VARIABLES = {
    "age": {
        "variable_name": "age",
        "entity_type": "person",
        "source": "household_input",
        "period_granularity": "year",
        "entity_count": 2,
        "period_count": 1,
        "occurrence_count": 2,
        "availability_status": "supported",
        "variable_name_truncated": False,
    },
    "employment_income": {
        "variable_name": "employment_income",
        "entity_type": "person",
        "source": "household_input",
        "period_granularity": "year",
        "entity_count": 1,
        "period_count": 1,
        "occurrence_count": 1,
        "availability_status": "supported",
        "variable_name_truncated": False,
    },
    "state_name": {
        "variable_name": "state_name",
        "entity_type": "household",
        "source": "household_input",
        "period_granularity": "year",
        "entity_count": 1,
        "period_count": 1,
        "occurrence_count": 1,
        "availability_status": "supported",
        "variable_name_truncated": False,
    },
    "ctc": {
        "variable_name": "ctc",
        "entity_type": "tax_unit",
        "source": "requested_output",
        "period_granularity": "year",
        "entity_count": 1,
        "period_count": 1,
        "occurrence_count": 1,
        "availability_status": "supported",
        "variable_name_truncated": False,
    },
}


def test_calculate_request_records_complete_analytics_metadata(
    deployed_api,
    auth_token,
    request_version,
    expected_channel,
    route_mode,
):
    if not expected_channel or not route_mode:
        pytest.skip(
            "Modal route metadata is only asserted in Modal route tests"
        )

    resolved_channel = _expected_resolved_channel(
        deployed_api,
        request_version,
        expected_channel,
        route_mode,
    )
    requested_version = request_version or "current"
    start_time = datetime.now(timezone.utc) - timedelta(seconds=5)

    calculate_response = deployed_api.post(
        "/us/calculate",
        headers={"Authorization": f"Bearer {auth_token}"},
        json_body=_calculate_request_body(requested_version),
    )

    assert calculate_response.status_code == 200

    analytics_request = _wait_for_analytics_request(
        deployed_api,
        auth_token,
        start_time=start_time,
        requested_version=requested_version,
        resolved_channel=resolved_channel,
    )

    _assert_request_metadata(
        analytics_request,
        requested_version=requested_version,
        resolved_channel=resolved_channel,
    )


def _expected_resolved_channel(
    deployed_api,
    request_version: str | None,
    expected_channel: str,
    route_mode: str,
) -> str:
    if route_mode == "channel":
        return expected_channel

    if route_mode != "exact":
        raise AssertionError(f"Unexpected route mode: {route_mode}")

    versions_response = deployed_api.get("/versions/us")
    assert versions_response.status_code == 200
    versions = versions_response.json()
    for channel in ("current", "frontier"):
        if versions.get(channel) == request_version:
            return channel

    raise AssertionError(
        f"No active channel serves US package version {request_version}"
    )


def _calculate_request_body(requested_version: str) -> dict[str, Any]:
    return {
        "version": requested_version,
        "household": {
            "people": {
                "parent": {
                    "age": {"2026": 35},
                    "employment_income": {"2026": 60_000},
                },
                "child": {
                    "age": {"2026": 6},
                },
            },
            "tax_units": {
                "tax_unit": {
                    "members": ["parent", "child"],
                    "ctc": {"2026": None},
                },
            },
            "spm_units": {
                "spm_unit": {
                    "members": ["parent", "child"],
                },
            },
            "households": {
                "household": {
                    "members": ["parent", "child"],
                    "state_name": {"2026": "AZ"},
                },
            },
        },
    }


def _wait_for_analytics_request(
    deployed_api,
    auth_token: str,
    *,
    start_time: datetime,
    requested_version: str,
    resolved_channel: str,
) -> dict[str, Any]:
    for _ in range(5):
        payload = _analytics_payload(
            deployed_api,
            auth_token,
            start_time=start_time,
            requested_version=requested_version,
            resolved_channel=resolved_channel,
        )
        request_record = _matching_request(payload)
        if request_record is not None:
            return request_record
        sleep(1)

    raise AssertionError(
        "Calculate analytics request was not returned with the expected "
        f"metadata. Last payload: {payload}"
    )


def _analytics_payload(
    deployed_api,
    auth_token: str,
    *,
    start_time: datetime,
    requested_version: str,
    resolved_channel: str,
) -> dict[str, Any]:
    query = urlencode(
        {
            "start_time": _isoformat_utc(start_time),
            "requested_version": requested_version,
            "resolved_channel": resolved_channel,
            "limit": "20",
        }
    )
    response = deployed_api.get(
        f"/analytics/calculate/requests?{query}",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert response.status_code == 200

    payload = response.json()
    assert set(payload) == TOP_LEVEL_ANALYTICS_KEYS
    assert payload["status"] == "ok"
    assert payload["message"] is None
    assert payload["start_time"] == _isoformat_utc(start_time)
    assert payload["end_time"] is None
    assert payload["requested_version"] == requested_version
    assert payload["resolved_channel"] == resolved_channel
    assert payload["unique"] is False
    assert isinstance(payload["requests"], list)
    return payload


def _matching_request(payload: dict[str, Any]) -> dict[str, Any] | None:
    expected_variable_names = set(EXPECTED_VARIABLES)
    for request_record in payload["requests"]:
        variables = request_record.get("variables", [])
        variable_names = {
            variable.get("variable_name") for variable in variables
        }
        if variable_names == expected_variable_names:
            return request_record
    return None


def _assert_request_metadata(
    request_record: dict[str, Any],
    *,
    requested_version: str,
    resolved_channel: str,
) -> None:
    assert set(request_record) == REQUEST_ANALYTICS_KEYS
    UUID(request_record["request_uuid"])
    assert _parse_api_datetime(request_record["created_at"])
    assert isinstance(request_record["api_version"], str)
    assert request_record["api_version"]
    assert request_record["country_id"] == "us"
    assert isinstance(request_record["model_version"], str)
    assert request_record["model_version"]
    assert request_record["requested_version"] == requested_version
    assert request_record["resolved_channel"] == resolved_channel
    assert request_record["endpoint"] == "calculate"
    assert request_record["method"] == "POST"
    assert request_record["response_status_code"] == 200
    assert request_record["distinct_variable_count"] == len(EXPECTED_VARIABLES)
    assert request_record["unsupported_variable_count"] == 0
    assert request_record["deprecated_allowlisted_variable_count"] == 0

    variables_by_name = {
        variable["variable_name"]: variable
        for variable in request_record["variables"]
    }
    assert variables_by_name == EXPECTED_VARIABLES
    for variable in variables_by_name.values():
        assert set(variable) == VARIABLE_ANALYTICS_KEYS


def _isoformat_utc(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc).replace(tzinfo=None).isoformat() + "Z"
    )


def _parse_api_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
