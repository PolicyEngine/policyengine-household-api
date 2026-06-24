from __future__ import annotations

from typing import Any, Iterable, Mapping


VERSION_CHANNELS = ("current", "frontier")


class VersionRoutingError(ValueError):
    status_code: int = 400
    code: str | None = None
    requested_version: str | None = None
    country_id: str | None = None
    available_versions: dict[str, str] | None = None

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str | None = None,
        requested_version: str | None = None,
        country_id: str | None = None,
        available_versions: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        if status_code is not None:
            self.status_code = status_code
        self.code = code
        self.requested_version = requested_version
        self.country_id = country_id
        self.available_versions = available_versions


class UnsupportedVersionError(VersionRoutingError):
    def __init__(
        self,
        *,
        country_id: str,
        requested_version: str,
        available_versions: dict[str, str],
        active_target_label: str,
    ) -> None:
        super().__init__(
            f"No active {active_target_label} serves `{country_id}` package "
            f"version `{requested_version}`",
            status_code=422,
            code="unsupported_version",
            requested_version=requested_version,
            country_id=country_id,
            available_versions=available_versions,
        )


class DeprecatedVersionError(VersionRoutingError):
    def __init__(
        self,
        *,
        country_id: str,
        requested_version: str,
        available_versions: dict[str, str],
    ) -> None:
        super().__init__(
            f"Household API `{country_id}` package version "
            f"`{requested_version}` is deprecated",
            status_code=422,
            code="deprecated_version",
            requested_version=requested_version,
            country_id=country_id,
            available_versions=available_versions,
        )


def active_versions_for_country(
    channel_references: Mapping[str, Mapping[str, Any] | None],
    country_id: str,
    channels: Iterable[str] = VERSION_CHANNELS,
) -> dict[str, str]:
    active_versions = {}
    for channel in channels:
        reference = channel_references.get(channel)
        if not reference:
            continue
        package_version = reference["package_versions"].get(country_id)
        if package_version:
            active_versions[channel] = package_version
    return active_versions


def retired_version_exists(
    references: Iterable[Mapping[str, Any]],
    country_id: str,
    requested_version: str,
) -> bool:
    for reference in references:
        package_versions = reference.get("package_versions", {})
        if not isinstance(package_versions, Mapping):
            continue
        if package_versions.get(country_id) == requested_version:
            return True
    return False


def package_versions_from_mapping(
    package_versions: Mapping[str, Any],
) -> dict[str, str]:
    return {
        country: version
        for country, version in package_versions.items()
        if isinstance(country, str)
        and isinstance(version, str)
        and country
        and version
    }
