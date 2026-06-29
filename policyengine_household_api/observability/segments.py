from __future__ import annotations

from enum import StrEnum
from typing import Any

from policyengine_observability import UNKNOWN_SEGMENT
from policyengine_observability import coerce_segment_name as _coerce_segment


class SegmentName(StrEnum):
    UNKNOWN = UNKNOWN_SEGMENT

    REQUEST_PARSE = "request_parse"
    PAYLOAD_VALIDATION = "payload_validation"
    VARIABLE_VALIDATION = "variable_validation"
    DEPRECATED_INPUT_FILTER = "deprecated_input_filter"
    PERIOD_VALIDATION = "period_validation"
    PERIOD_WARNING_DETECTION = "period_warning_detection"
    CALCULATION = "calculation"
    RESPONSE_SERIALIZATION = "response_serialization"

    ANALYTICS_CONTEXT_BUILD = "analytics_context_build"
    ANALYTICS_WRITE = "analytics_write"
    AUTH = "auth"

    MANIFEST_LOAD = "manifest_load"
    VERSION_RESOLUTION = "version_resolution"
    WORKER_DISPATCH = "worker_dispatch"
    MODAL_WORKER_LOOKUP = "modal_worker_lookup"
    MODAL_REMOTE_EXECUTION = "modal_remote_execution"
    CLOUD_RUN_AUTH = "cloud_run_auth"
    CLOUD_RUN_HTTP_REQUEST = "cloud_run_http_request"
    CLOUD_RUN_RESPONSE_DECODE = "cloud_run_response_decode"
    FALLBACK_WARMUP = "fallback_warmup"
    MODAL_STATUS_CHECK = "modal_status_check"
    CIRCUIT_REFRESH = "circuit_refresh"
    MODAL_REQUEST = "modal_request"
    MODAL_PROBE = "modal_probe"
    MODAL_CANARY = "modal_canary"
    CLOUD_RUN_REQUEST = "cloud_run_request"


def coerce_segment_name(value: Any) -> tuple[str, bool]:
    return _coerce_segment(value, registry=SegmentName)
