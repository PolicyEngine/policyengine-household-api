from __future__ import annotations

import concurrent.futures
from datetime import UTC
from datetime import datetime
import json
import logging
import os
import threading
import time
from typing import Any
from urllib import request as urllib_request


LOGGER = logging.getLogger(__name__)

SLACK_WEBHOOK_URL_ENV = "HOUSEHOLD_FAILOVER_SLACK_WEBHOOK_URL"
SLACK_TIMEOUT_SECONDS_ENV = "HOUSEHOLD_FAILOVER_SLACK_TIMEOUT_SECONDS"
SLACK_COOLDOWN_SECONDS_ENV = "HOUSEHOLD_FAILOVER_SLACK_COOLDOWN_SECONDS"

DEFAULT_SLACK_TIMEOUT_SECONDS = 2.0
DEFAULT_SLACK_COOLDOWN_SECONDS = 300.0

ALERT_EVENTS = frozenset(
    {
        "modal_circuit_opened",
        "fallback_selected",
        "backend_unavailable",
        "modal_circuit_recovered",
    }
)

EVENT_TITLES = {
    "modal_circuit_opened": "Modal circuit opened",
    "fallback_selected": "Cloud Run fallback selected",
    "backend_unavailable": "No healthy household API backend available",
    "modal_circuit_recovered": "Modal circuit recovered",
}

_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=2,
    thread_name_prefix="household-slack-failover",
)


class SlackFailoverNotifier:
    def __init__(
        self,
        *,
        executor: concurrent.futures.Executor | None = None,
        urlopen: Any | None = None,
        time_source: Any | None = None,
    ) -> None:
        self._executor = executor or _EXECUTOR
        self._urlopen = urlopen or urllib_request.urlopen
        self._time = time_source or time.monotonic
        self._last_sent_at: dict[tuple[str, ...], float] = {}
        self._lock = threading.Lock()

    def notify(self, event: str, **fields: Any) -> bool:
        if event not in ALERT_EVENTS:
            return False

        webhook_url = os.getenv(SLACK_WEBHOOK_URL_ENV, "").strip()
        if not webhook_url:
            return False

        cooldown_seconds = _float_env(
            SLACK_COOLDOWN_SECONDS_ENV,
            DEFAULT_SLACK_COOLDOWN_SECONDS,
        )
        dedupe_key = _dedupe_key(event, fields)
        should_send, cooldown_reserved_at = self._reserve_cooldown(
            dedupe_key,
            cooldown_seconds,
        )
        if not should_send:
            return False

        timeout_seconds = _float_env(
            SLACK_TIMEOUT_SECONDS_ENV,
            DEFAULT_SLACK_TIMEOUT_SECONDS,
            minimum=0.001,
        )
        payload = _build_payload(event, fields)
        try:
            self._executor.submit(
                self._send,
                webhook_url,
                payload,
                timeout_seconds,
            )
            return True
        except Exception as exc:
            self._clear_cooldown_reservation(
                dedupe_key,
                cooldown_reserved_at,
            )
            LOGGER.warning(
                "Failed to submit Slack failover alert",
                extra={"error_type": type(exc).__name__},
            )
            return False

    def _reserve_cooldown(
        self,
        dedupe_key: tuple[str, ...],
        cooldown_seconds: float,
    ) -> tuple[bool, float | None]:
        if cooldown_seconds <= 0:
            return True, None

        now = self._time()
        with self._lock:
            last_sent_at = self._last_sent_at.get(dedupe_key)
            if (
                last_sent_at is not None
                and now - last_sent_at < cooldown_seconds
            ):
                return False, None
            self._last_sent_at[dedupe_key] = now
            return True, now

    def _clear_cooldown_reservation(
        self,
        dedupe_key: tuple[str, ...],
        reserved_at: float | None,
    ) -> None:
        if reserved_at is None:
            return

        with self._lock:
            if self._last_sent_at.get(dedupe_key) == reserved_at:
                del self._last_sent_at[dedupe_key]

    def _send(
        self,
        webhook_url: str,
        payload: dict[str, Any],
        timeout_seconds: float,
    ) -> None:
        body = json.dumps(payload).encode("utf-8")
        slack_request = urllib_request.Request(
            webhook_url,
            data=body,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with self._urlopen(
                slack_request,
                timeout=timeout_seconds,
            ) as response:
                status = getattr(response, "status", 200)
                if int(status) >= 400:
                    LOGGER.warning(
                        "Slack failover alert returned an error status",
                        extra={"status_code": status},
                    )
        except Exception as exc:
            LOGGER.warning(
                "Failed to send Slack failover alert",
                extra={"error_type": type(exc).__name__},
            )


_DEFAULT_NOTIFIER = SlackFailoverNotifier()


def notify_failover_lifecycle_event(event: str, **fields: Any) -> bool:
    return _DEFAULT_NOTIFIER.notify(event, **fields)


def _build_payload(event: str, fields: dict[str, Any]) -> dict[str, Any]:
    title = EVENT_TITLES.get(event, event)
    environment = fields.get("environment") or _environment()
    backend = fields.get("backend")
    if event == "fallback_selected" and backend is None:
        backend = "cloud_run"

    field_values = [
        ("Environment", environment),
        ("Event", event),
        ("Channel", fields.get("channel")),
        ("Reason", fields.get("reason")),
        ("Backend", backend),
        ("Source", fields.get("source")),
        ("Cloud Run service", os.getenv("K_SERVICE")),
        ("Cloud Run revision", os.getenv("K_REVISION")),
        ("Created at", datetime.now(UTC).isoformat()),
    ]
    slack_fields = [
        _mrkdwn_field(label, value)
        for label, value in field_values
        if value is not None and str(value) != ""
    ]
    text = f"Household API failover: {title}"
    return {
        "text": text,
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{_escape_slack_text(text)}*",
                },
            },
            {
                "type": "section",
                "fields": slack_fields,
            },
        ],
    }


def _mrkdwn_field(label: str, value: Any) -> dict[str, str]:
    return {
        "type": "mrkdwn",
        "text": f"*{label}*\n{_escape_slack_text(str(value))}",
    }


def _escape_slack_text(value: str) -> str:
    return (
        value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def _environment() -> str:
    for key in (
        "OBSERVABILITY_ENVIRONMENT",
        "DEPLOYMENT_ENVIRONMENT",
        "APP_ENV",
        "MODAL_ENVIRONMENT",
    ):
        value = os.getenv(key)
        if value:
            return value
    return "unknown"


def _dedupe_key(event: str, fields: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        str(value or "")
        for value in (
            event,
            fields.get("channel"),
            fields.get("reason"),
            fields.get("backend"),
            fields.get("source"),
        )
    )


def _float_env(
    name: str,
    default: float,
    *,
    minimum: float = 0,
) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return max(float(value), minimum)
    except ValueError:
        LOGGER.warning(
            "Invalid Slack failover alert configuration; using default",
            extra={"env_var": name},
        )
        return default
