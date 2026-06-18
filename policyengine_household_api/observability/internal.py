from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import sys
import traceback
from typing import Any


INTERNAL_LOGGER_NAME = "policyengine_household_api.observability.internal"

_INTERNAL_LOGGER = logging.getLogger(INTERNAL_LOGGER_NAME)


class PlainMessageFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return record.getMessage()


def configure_internal_logger(level: int) -> None:
    _INTERNAL_LOGGER.setLevel(level)
    _INTERNAL_LOGGER.propagate = False
    if not _INTERNAL_LOGGER.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(PlainMessageFormatter())
        _INTERNAL_LOGGER.addHandler(handler)


def log_observability_failure(
    operation: str,
    exc: BaseException,
    **fields: Any,
) -> None:
    payload = {
        "schema_version": "policyengine.observability.internal_error.v1",
        "event": "observability_internal_error",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "operation": operation,
        "error": {
            "type": type(exc).__name__,
            "message": str(exc),
            "stack": "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            ),
        },
    }
    payload.update(
        {key: value for key, value in fields.items() if value is not None}
    )
    try:
        if not _INTERNAL_LOGGER.handlers:
            configure_internal_logger(logging.ERROR)
        _INTERNAL_LOGGER.error(_safe_json(payload))
    except Exception:
        _write_stderr(payload)


def _write_stderr(payload: dict[str, Any]) -> None:
    try:
        sys.stderr.write(_safe_json(payload) + "\n")
    except Exception:
        return


def _safe_json(payload: dict[str, Any]) -> str:
    try:
        return json.dumps(payload, sort_keys=True, default=str)
    except Exception as exc:
        return json.dumps(
            {
                "schema_version": "policyengine.observability.internal_error.v1",
                "event": "observability_internal_error",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "operation": "observability.failure_json",
                "error": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                },
            },
            sort_keys=True,
        )
