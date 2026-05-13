from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any, Mapping

from policyengine_household_api.constants import (
    COUNTRIES,
    COUNTRY_PACKAGE_VERSIONS,
)
from policyengine_household_api.data.analytics_setup import (
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


@dataclass(frozen=True)
class AppReference:
    app_name: str
    package_versions: dict[str, str]
    deployed_at: str
    source_commit: str | None = None
    analytics_migration_minimum_revision: str | None = None
    analytics_database_revision: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = {
            "app_name": self.app_name,
            "package_versions": dict(self.package_versions),
            "deployed_at": self.deployed_at,
        }
        if self.source_commit:
            data["source_commit"] = self.source_commit
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
    return dict(COUNTRY_PACKAGE_VERSIONS)


def build_app_name(
    package_versions: Mapping[str, str] | None = None,
) -> str:
    versions = package_versions or current_package_versions()
    version_slug = "-".join(
        f"{country}{_slugify_version(versions[country])}"
        for country in COUNTRIES
        if country in versions
    )
    return f"{APP_NAME_PREFIX}-{version_slug}"


def build_app_reference(
    *,
    app_name: str | None = None,
    package_versions: Mapping[str, str] | None = None,
    source_commit: str | None = None,
    deployed_at: str | None = None,
    analytics_database_revision: str | None = None,
) -> dict[str, Any]:
    versions = dict(package_versions or current_package_versions())
    reference = AppReference(
        app_name=app_name or build_app_name(versions),
        package_versions=versions,
        deployed_at=deployed_at or current_timestamp(),
        source_commit=source_commit,
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


def normalize_manifest(manifest: Mapping[str, Any] | None) -> dict[str, Any]:
    if not manifest:
        return empty_manifest()

    normalized = deepcopy(dict(manifest))
    normalized.setdefault("schema_version", MANIFEST_SCHEMA_VERSION)
    normalized.setdefault("current", None)
    normalized.setdefault("frontier", None)
    normalized.setdefault("retired", [])

    if normalized["schema_version"] != MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            "Unsupported household API Modal manifest schema version: "
            f"{normalized['schema_version']}"
        )
    if normalized["retired"] is None:
        normalized["retired"] = []
    if not isinstance(normalized["retired"], list):
        raise ValueError("Modal manifest `retired` field must be a list")

    return normalized


def apply_release_config(
    manifest: Mapping[str, Any] | None,
    config: ModalReleaseConfig,
    *,
    new_app: Mapping[str, Any] | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    next_manifest = normalize_manifest(manifest)
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
    return next_manifest


def cleanup_app_names_for_target(
    manifest: Mapping[str, Any],
    target: CleanupTarget,
) -> list[str]:
    normalized = normalize_manifest(manifest)
    active_app_names = {
        app["app_name"]
        for app in (
            normalized.get("current"),
            normalized.get("frontier"),
        )
        if isinstance(app, dict) and app.get("app_name")
    }

    if target == CleanupTarget.NONE:
        return []
    if target == CleanupTarget.RETIRED:
        names = [
            app["app_name"]
            for app in normalized.get("retired", [])
            if isinstance(app, dict) and app.get("app_name")
        ]
        return [name for name in names if name not in active_app_names]

    channel = normalized.get(target.value)
    if not channel:
        return []
    app_name = channel.get("app_name")
    if app_name in active_app_names:
        raise ValueError(
            f"Refusing to clean up active `{target.value}` app `{app_name}`"
        )
    return [app_name] if app_name else []


def prune_cleaned_retired_apps(
    manifest: Mapping[str, Any],
    app_names: set[str],
) -> dict[str, Any]:
    normalized = normalize_manifest(manifest)
    normalized["retired"] = [
        app
        for app in normalized["retired"]
        if not isinstance(app, dict) or app.get("app_name") not in app_names
    ]
    return normalized


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


def _slugify_version(version: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", version).strip("-").lower()
    return slug or "unknown"
