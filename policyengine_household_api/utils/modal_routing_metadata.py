from __future__ import annotations

from typing import Any

from policyengine_household_api.models.analytics import ModalResolvedChannel


MODAL_ROUTING_PAYLOAD_KEY = "modal_routing"
REQUESTED_VERSION_ENVIRON_KEY = "policyengine.requested_version"
RESOLVED_CHANNEL_ENVIRON_KEY = "policyengine.resolved_channel"


def modal_routing_payload(
    *,
    requested_version: str,
    resolved_channel: str,
) -> dict[str, str]:
    return {
        "requested_version": requested_version,
        "resolved_channel": resolved_channel,
    }


def routing_environ_overrides(payload: dict[str, Any]) -> dict[str, str]:
    routing = payload.get(MODAL_ROUTING_PAYLOAD_KEY)
    if not isinstance(routing, dict):
        return {}

    requested_version = routing.get("requested_version")
    resolved_channel = routing.get("resolved_channel")
    if not isinstance(requested_version, str) or not requested_version:
        return {}
    if resolved_channel not in {
        channel.value for channel in ModalResolvedChannel
    }:
        return {}

    return {
        REQUESTED_VERSION_ENVIRON_KEY: requested_version,
        RESOLVED_CHANNEL_ENVIRON_KEY: resolved_channel,
    }
