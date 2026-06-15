"""Shared request-size limits for the Cloud Run failover services.

Both the gateway and the worker run on Cloud Run, whose HTTP/1 request body
limit is 32 MiB. We cap ``MAX_CONTENT_LENGTH`` at that platform limit so a
single request cannot force either container to buffer an unbounded body. The
cap is overridable (in bytes) via ``HOUSEHOLD_FAILOVER_MAX_CONTENT_LENGTH`` for
load testing or future tuning.
"""

from __future__ import annotations

import os

MAX_CONTENT_LENGTH_ENV = "HOUSEHOLD_FAILOVER_MAX_CONTENT_LENGTH"
DEFAULT_MAX_CONTENT_LENGTH_BYTES = 32 * 1024 * 1024


def max_content_length_bytes() -> int:
    raw_value = os.getenv(MAX_CONTENT_LENGTH_ENV, "")
    if not raw_value:
        return DEFAULT_MAX_CONTENT_LENGTH_BYTES
    try:
        value = int(raw_value)
    except ValueError:
        return DEFAULT_MAX_CONTENT_LENGTH_BYTES
    return value if value > 0 else DEFAULT_MAX_CONTENT_LENGTH_BYTES
