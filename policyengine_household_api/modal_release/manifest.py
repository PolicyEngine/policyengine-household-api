from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any, Mapping

from policyengine_household_api.constants import COUNTRY_PACKAGE_VERSIONS
from policyengine_household_api.data.analytics_migration import (
    ANALYTICS_ALEMBIC_MINIMUM_REVISION,
)
from policyengine_household_api.modal_release.release_config import (
    CleanupTarget,
    ModalReleaseConfig,
    NewAppTarget,
)


MANIFEST_SCHEMA_VERSION = 1
MANIFEST_DICT_NAME = "household-api-release-manifest"
MANIFEST_DICT_KEY = "manifest"
APP_NAME_PREFIX = "policyengine-household-api"
RELEASE_PACKAGE_VERSION_COUNTRIES = ("uk", "us")
APP_REFERENCE_KEYS = {
    "app_name",
    "package_versions",
    "deployed_at",
    "analytics_migration_minimum_revision",
    "analytics_database_revision",
}
RETIRED_APP_REFERENCE_KEYS = APP_REFERENCE_KEYS | {
    "retired_at",
    "retirement_reason",
}
APP_REFERENCE_REQUIRED_KEYS = {
    "app_name",
    "package_versions",
    "deployed_at",
}
MANIFEST_KEYS = {
    "schema_version",
    "current",
    "frontier",
    "retired",
}


@dataclass(frozen=True)
class AppReference:
    app_name: str
    package_versions: dict[str, str]
    deployed_at: str
    analytics_migration_minimum_revision: str | None = None
    analytics_database_revision: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = {
            "app_name": self.app_name,
            "package_versions": dict(self.package_versions),
            "deployed_at": self.deployed_at,
        }
        if self.analytics_migration_minimum_revision:
            data["analytics_migration_minimum_revision"] = (
                self.analytics_migration_minimum_revision
            )
        if self.analytics_database_revision:
            data["analytics_database_revision"] = (
                self.analytics_database_revision
            )
        return data


def current_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_package_versions() -> dict[str, str]:
    return _release_package_versions_from_mapping(COUNTRY_PACKAGE_VERSIONS)


def build_app_name(
    package_versions: Mapping[str, str] | None = None,
) -> str:
    versions = (
        _canonical_release_package_versions(package_versions)
        if package_versions is not None
        else _canonical_release_package_versions(current_package_versions())
    )
    version_slug = "-".join(
        f"{country}{_slugify_version(versions[country])}"
        for country in RELEASE_PACKAGE_VERSION_COUNTRIES
    )
    return f"{APP_NAME_PREFIX}-{version_slug}"


def build_app_reference(
    *,
    app_name: str | None = None,
    package_versions: Mapping[str, str] | None = None,
    deployed_at: str | None = None,
    analytics_database_revision: str | None = None,
) -> dict[str, Any]:
    versions = _canonical_release_package_versions(
        package_versions
        if package_versions is not None
        else current_package_versions()
    )
    reference = AppReference(
        app_name=app_name or build_app_name(versions),
        package_versions=versions,
        deployed_at=deployed_at or current_timestamp(),
        analytics_migration_minimum_revision=(
            ANALYTICS_ALEMBIC_MINIMUM_REVISION
        ),
        analytics_database_revision=analytics_database_revision,
    )
    return reference.to_dict()


def empty_manifest() -> dict[str, Any]:
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "current": None,
        "frontier": None,
        "retired": [],
    }


def validate_manifest(manifest: Mapping[str, Any] | None) -> dict[str, Any]:
    if manifest is None:
        return empty_manifest()
    if not isinstance(manifest, Mapping):
        raise ValueError("Modal manifest must be a mapping")

    validated = deepcopy(dict(manifest))
    _validate_manifest_keys(validated)

    if validated.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            "Unsupported household API Modal manifest schema version: "
            f"{validated.get('schema_version')}"
        )

    validated["current"] = _validate_app_reference(validated["current"])
    validated["frontier"] = _validate_app_reference(validated["frontier"])
    if not isinstance(validated["retired"], list):
        raise ValueError("Modal manifest `retired` field must be a list")
    retired = []
    for app in validated["retired"]:
        validated_entry = _validate_app_reference(
            app,
            allow_retirement_metadata=True,
        )
        if validated_entry is not None:
            retired.append(validated_entry)
    validated["retired"] = retired

    return validated


def apply_release_config(
    manifest: Mapping[str, Any] | None,
    config: ModalReleaseConfig,
    *,
    new_app: Mapping[str, Any] | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    next_manifest = validate_manifest(manifest)
    retired = list(next_manifest["retired"])
    retired_at = timestamp or current_timestamp()

    if config.deploys_new_app and new_app is None:
        raise ValueError("A new app reference is required for this release")

    if config.new_app_target == NewAppTarget.FRONTIER:
        if config.promote_existing_frontier:
            retired = _retire_entry(
                retired,
                next_manifest.get("current"),
                retired_at=retired_at,
                reason="replaced-current",
            )
            next_manifest["current"] = next_manifest.get("frontier")
        else:
            retired = _retire_entry(
                retired,
                next_manifest.get("frontier"),
                retired_at=retired_at,
                reason="replaced-frontier",
            )
        next_manifest["frontier"] = deepcopy(dict(new_app or {}))

    elif config.new_app_target == NewAppTarget.CURRENT:
        retired = _retire_entry(
            retired,
            next_manifest.get("current"),
            retired_at=retired_at,
            reason="replaced-current",
        )
        retired = _retire_entry(
            retired,
            next_manifest.get("frontier"),
            retired_at=retired_at,
            reason="frontier-cleared",
        )
        next_manifest["current"] = deepcopy(dict(new_app or {}))
        next_manifest["frontier"] = None

    next_manifest["retired"] = retired
    return validate_manifest(next_manifest)


def cleanup_app_names_for_target(
    manifest: Mapping[str, Any],
    target: CleanupTarget,
    *,
    previous_manifest: Mapping[str, Any] | None = None,
) -> list[str]:
    validated = validate_manifest(manifest)
    active_app_names = {
        app["app_name"]
        for app in (
            validated.get("current"),
            validated.get("frontier"),
        )
        if isinstance(app, dict) and app.get("app_name")
    }

    if target == CleanupTarget.NONE:
        return []
    if target == CleanupTarget.RETIRED:
        names = [
            app["app_name"]
            for app in validated.get("retired", [])
            if isinstance(app, dict) and app.get("app_name")
        ]
        return _unique_app_names(
            name for name in names if name not in active_app_names
        )

    if previous_manifest is not None:
        previous = validate_manifest(previous_manifest)
        previous_channel = previous.get(target.value)
        if not previous_channel:
            return []
        app_name = previous_channel.get("app_name")
        if app_name in active_app_names:
            raise ValueError(
                f"Refusing to clean up active `{target.value}` app "
                f"`{app_name}`"
            )
        return [app_name] if app_name else []

    channel = validated.get(target.value)
    if not channel:
        return []
    app_name = channel.get("app_name")
    if app_name in active_app_names:
        raise ValueError(
            f"Refusing to clean up active `{target.value}` app `{app_name}`"
        )
    return [app_name] if app_name else []


def active_app_deployments(
    manifest: Mapping[str, Any],
) -> list[dict[str, Any]]:
    validated = validate_manifest(manifest)
    deployments_by_name: dict[str, dict[str, str]] = {}

    for channel in ("current", "frontier"):
        app_reference = validated.get(channel)
        if not app_reference:
            continue
        app_name = app_reference.get("app_name")
        if not app_name:
            continue
        package_versions = _required_release_package_versions(
            app_reference.get("package_versions", {}),
            app_name=app_name,
            channel=channel,
        )
        if (
            app_name in deployments_by_name
            and deployments_by_name[app_name] != package_versions
        ):
            raise ValueError(
                f"Active Modal app `{app_name}` has conflicting package "
                "versions in current/frontier manifest entries"
            )
        deployments_by_name[app_name] = package_versions

    if not deployments_by_name:
        raise ValueError("No active Modal household API apps are configured")

    return [
        {
            "app_name": app_name,
            "package_versions": package_versions,
        }
        for app_name, package_versions in deployments_by_name.items()
    ]


def prune_cleaned_retired_apps(
    manifest: Mapping[str, Any],
    app_names: set[str],
) -> dict[str, Any]:
    validated = validate_manifest(manifest)
    validated["retired"] = [
        app
        for app in validated["retired"]
        if not isinstance(app, dict) or app.get("app_name") not in app_names
    ]
    return validated


def rewrite_manifest_for_storage(
    manifest: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if manifest is None:
        return empty_manifest()
    if not isinstance(manifest, Mapping):
        raise ValueError("Modal manifest must be a mapping")

    rewritten = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "current": _rewrite_legacy_app_reference(manifest.get("current")),
        "frontier": _rewrite_legacy_app_reference(manifest.get("frontier")),
        "retired": [],
    }
    return validate_manifest(rewritten)


def rewrite_existing_manifest_for_storage(
    manifest: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not manifest:
        raise ValueError("Cannot rewrite a missing Modal release manifest")

    rewritten_manifest = rewrite_manifest_for_storage(manifest)
    if not rewritten_manifest.get("current") and not rewritten_manifest.get(
        "frontier"
    ):
        raise ValueError(
            "Cannot rewrite a Modal release manifest without an active "
            "`current` or `frontier` app"
        )
    active_app_deployments(rewritten_manifest)
    return rewritten_manifest


def _retire_entry(
    retired: list[dict[str, Any]],
    entry: Mapping[str, Any] | None,
    *,
    retired_at: str,
    reason: str,
) -> list[dict[str, Any]]:
    if not entry:
        return retired

    retired_entry = deepcopy(dict(entry))
    retired_entry["retired_at"] = retired_at
    retired_entry["retirement_reason"] = reason
    return retired + [retired_entry]


def _validate_app_reference(
    entry: Any,
    *,
    allow_retirement_metadata: bool = False,
) -> dict[str, Any] | None:
    if entry is None:
        return None
    if not isinstance(entry, Mapping):
        raise ValueError("Modal manifest app references must be mappings")

    validated = deepcopy(dict(entry))
    _validate_app_reference_keys(
        validated,
        allow_retirement_metadata=allow_retirement_metadata,
    )
    _validate_required_string(validated, "app_name")
    _validate_required_string(validated, "deployed_at")
    validated["package_versions"] = _canonical_release_package_versions(
        validated["package_versions"]
    )
    return validated


def _rewrite_legacy_app_reference(entry: Any) -> dict[str, Any] | None:
    if entry is None:
        return None
    if not isinstance(entry, Mapping):
        raise ValueError("Modal manifest app references must be mappings")

    package_versions = _release_package_versions_from_mapping(
        entry.get("package_versions", {})
    )
    rewritten = {
        "app_name": entry.get("app_name"),
        "package_versions": _canonical_release_package_versions(
            package_versions
        ),
        "deployed_at": entry.get("deployed_at"),
    }
    for key in (
        "analytics_migration_minimum_revision",
        "analytics_database_revision",
    ):
        if entry.get(key):
            rewritten[key] = entry[key]
    return _validate_app_reference(rewritten)


def _unique_app_names(app_names) -> list[str]:
    seen = set()
    unique_names = []
    for app_name in app_names:
        if app_name in seen:
            continue
        seen.add(app_name)
        unique_names.append(app_name)
    return unique_names


def _slugify_version(version: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", version).strip("-").lower()
    return slug or "unknown"


def _release_package_versions_from_mapping(
    package_versions: Mapping[str, str],
) -> dict[str, str]:
    if not isinstance(package_versions, Mapping):
        raise ValueError("Modal manifest `package_versions` must be a mapping")
    return {
        country: version
        for country in RELEASE_PACKAGE_VERSION_COUNTRIES
        if country in package_versions
        and isinstance(version := package_versions[country], str)
        and version
    }


def _canonical_release_package_versions(
    package_versions: Mapping[str, str],
) -> dict[str, str]:
    versions = _release_package_versions_from_mapping(package_versions)
    unexpected_countries = [
        country
        for country in package_versions
        if country not in RELEASE_PACKAGE_VERSION_COUNTRIES
    ]
    if unexpected_countries:
        unexpected = ", ".join(sorted(unexpected_countries))
        raise ValueError(
            "Modal manifest `package_versions` contains unsupported "
            f"country key(s): {unexpected}"
        )
    missing_countries = [
        country
        for country in RELEASE_PACKAGE_VERSION_COUNTRIES
        if country not in versions
    ]
    if missing_countries:
        missing = ", ".join(missing_countries)
        raise ValueError(
            "Modal manifest `package_versions` must declare release "
            f"package version(s): {missing}"
        )
    return versions


def _required_release_package_versions(
    package_versions: Mapping[str, str],
    *,
    app_name: str,
    channel: str,
) -> dict[str, str]:
    try:
        return _canonical_release_package_versions(package_versions)
    except ValueError as e:
        raise ValueError(
            f"Active Modal app `{app_name}` in `{channel}` must declare "
            "canonical release package versions"
        ) from e


def _validate_manifest_keys(manifest: Mapping[str, Any]) -> None:
    missing_keys = sorted(MANIFEST_KEYS - set(manifest))
    if missing_keys:
        keys = ", ".join(missing_keys)
        raise ValueError(f"Modal manifest is missing required key(s): {keys}")

    unsupported_keys = sorted(set(manifest) - MANIFEST_KEYS)
    if unsupported_keys:
        keys = ", ".join(unsupported_keys)
        raise ValueError(f"Modal manifest contains unsupported key(s): {keys}")


def _validate_app_reference_keys(
    entry: Mapping[str, Any],
    *,
    allow_retirement_metadata: bool,
) -> None:
    allowed_keys = (
        RETIRED_APP_REFERENCE_KEYS
        if allow_retirement_metadata
        else APP_REFERENCE_KEYS
    )
    unsupported_keys = sorted(set(entry) - allowed_keys)
    if unsupported_keys:
        keys = ", ".join(unsupported_keys)
        raise ValueError(
            f"Modal manifest app reference contains unsupported key(s): {keys}"
        )

    missing_keys = sorted(APP_REFERENCE_REQUIRED_KEYS - set(entry))
    if missing_keys:
        keys = ", ".join(missing_keys)
        raise ValueError(
            f"Modal manifest app reference is missing required key(s): {keys}"
        )


def _validate_required_string(entry: Mapping[str, Any], key: str) -> None:
    if not isinstance(entry.get(key), str) or not entry[key]:
        raise ValueError(
            f"Modal manifest app reference `{key}` must be a non-empty string"
        )
