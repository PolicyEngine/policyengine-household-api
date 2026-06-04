from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping


FAILOVER_MANIFEST_SCHEMA_VERSION = 1
FAILOVER_MANIFEST_BUCKET_ENV = "HOUSEHOLD_FAILOVER_MANIFEST_BUCKET"
FAILOVER_MANIFEST_BLOB_ENV = "HOUSEHOLD_FAILOVER_MANIFEST_BLOB"
FAILOVER_CHANNELS = ("current", "frontier")

CHANNEL_REQUIRED_KEYS = {
    "modal_app_name",
    "cloud_run_worker_url",
    "package_versions",
}
CHANNEL_OPTIONAL_KEYS = {
    "deployed_at",
    "analytics_migration_minimum_revision",
    "analytics_database_revision",
}
CHANNEL_KEYS = CHANNEL_REQUIRED_KEYS | CHANNEL_OPTIONAL_KEYS
MANIFEST_KEYS = {
    "schema_version",
    "environment",
    "generated_at",
    "channels",
}


@dataclass(frozen=True)
class ResolvedFailoverChannel:
    channel: str
    requested_version: str
    modal_app_name: str
    cloud_run_worker_url: str
    package_versions: dict[str, str]


class FailoverManifestError(ValueError):
    pass


class FailoverManifestUnavailable(FailoverManifestError):
    pass


class FailoverRoutingError(FailoverManifestError):
    pass


def current_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_failover_manifest(
    manifest: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if manifest is None:
        raise FailoverManifestError("Failover manifest is missing")
    if not isinstance(manifest, Mapping):
        raise FailoverManifestError("Failover manifest must be a mapping")

    validated = deepcopy(dict(manifest))
    _validate_keys(validated, MANIFEST_KEYS, "Failover manifest")
    if validated.get("schema_version") != FAILOVER_MANIFEST_SCHEMA_VERSION:
        raise FailoverManifestError(
            "Unsupported failover manifest schema version: "
            f"{validated.get('schema_version')}"
        )
    if not isinstance(validated.get("environment"), str):
        raise FailoverManifestError("Failover manifest environment is invalid")
    if not isinstance(validated.get("generated_at"), str):
        raise FailoverManifestError(
            "Failover manifest generated_at is invalid"
        )

    channels = validated.get("channels")
    if not isinstance(channels, Mapping):
        raise FailoverManifestError("Failover manifest channels are invalid")

    validated_channels = {}
    for channel in FAILOVER_CHANNELS:
        reference = channels.get(channel)
        if reference is None:
            validated_channels[channel] = None
        else:
            validated_channels[channel] = _validate_channel_reference(
                channel,
                reference,
            )
    validated["channels"] = validated_channels
    return validated


def build_failover_manifest(
    *,
    environment: str,
    modal_manifest: Mapping[str, Any],
    worker_urls: Mapping[str, str],
    generated_at: str | None = None,
) -> dict[str, Any]:
    channels: dict[str, dict[str, Any] | None] = {}
    for channel in FAILOVER_CHANNELS:
        modal_reference = modal_manifest.get(channel)
        if not modal_reference:
            channels[channel] = None
            continue

        channel_reference = {
            "modal_app_name": modal_reference["app_name"],
            "cloud_run_worker_url": worker_urls[channel],
            "package_versions": dict(modal_reference["package_versions"]),
        }
        for key in CHANNEL_OPTIONAL_KEYS:
            value = modal_reference.get(key)
            if value:
                channel_reference[key] = value
        channels[channel] = channel_reference

    return validate_failover_manifest(
        {
            "schema_version": FAILOVER_MANIFEST_SCHEMA_VERSION,
            "environment": environment,
            "generated_at": generated_at or current_timestamp(),
            "channels": channels,
        }
    )


def resolve_failover_channel_for_request(
    manifest: Mapping[str, Any],
    *,
    country_id: str | None,
    requested_version: str | None,
) -> ResolvedFailoverChannel:
    validated = validate_failover_manifest(manifest)
    requested = requested_version or "current"
    channels = validated["channels"]

    if requested in FAILOVER_CHANNELS:
        reference = channels.get(requested)
        if not reference:
            raise FailoverManifestUnavailable(
                f"No `{requested}` failover channel is configured"
            )
        return _resolved_channel(requested, requested, reference)

    if not country_id:
        raise FailoverRoutingError(
            "Exact package version routing requires a country endpoint"
        )

    for channel in FAILOVER_CHANNELS:
        reference = channels.get(channel)
        if not reference:
            continue
        if reference["package_versions"].get(country_id) == requested:
            return _resolved_channel(channel, requested, reference)

    raise FailoverRoutingError(
        f"No active failover channel serves `{country_id}` package "
        f"version `{requested}`"
    )


def _validate_channel_reference(
    channel: str,
    reference: Any,
) -> dict[str, Any]:
    if not isinstance(reference, Mapping):
        raise FailoverManifestError(
            f"Failover channel `{channel}` must be a mapping"
        )

    validated = deepcopy(dict(reference))
    _validate_keys(validated, CHANNEL_KEYS, f"Failover channel `{channel}`")
    missing = CHANNEL_REQUIRED_KEYS - validated.keys()
    if missing:
        raise FailoverManifestError(
            f"Failover channel `{channel}` is missing: {sorted(missing)}"
        )

    for key in ("modal_app_name", "cloud_run_worker_url"):
        if not isinstance(validated[key], str) or not validated[key]:
            raise FailoverManifestError(
                f"Failover channel `{channel}` has invalid `{key}`"
            )

    package_versions = validated["package_versions"]
    if not isinstance(package_versions, Mapping):
        raise FailoverManifestError(
            f"Failover channel `{channel}` package_versions must be a mapping"
        )
    validated["package_versions"] = {
        country: version
        for country, version in package_versions.items()
        if isinstance(country, str)
        and isinstance(version, str)
        and country
        and version
    }
    if not validated["package_versions"]:
        raise FailoverManifestError(
            f"Failover channel `{channel}` has no package versions"
        )
    return validated


def _validate_keys(
    mapping: Mapping[str, Any],
    allowed: set[str],
    label: str,
) -> None:
    extra = set(mapping) - allowed
    if extra:
        raise FailoverManifestError(
            f"{label} contains unsupported keys: {sorted(extra)}"
        )


def _resolved_channel(
    channel: str,
    requested_version: str,
    reference: Mapping[str, Any],
) -> ResolvedFailoverChannel:
    return ResolvedFailoverChannel(
        channel=channel,
        requested_version=requested_version,
        modal_app_name=reference["modal_app_name"],
        cloud_run_worker_url=reference["cloud_run_worker_url"],
        package_versions=dict(reference["package_versions"]),
    )
