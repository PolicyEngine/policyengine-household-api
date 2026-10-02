from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
import json
from types import MappingProxyType


class WorkerResourceProfile(StrEnum):
    CURRENT = "current"
    FRONTIER = "frontier"


@dataclass(frozen=True)
class WorkerDeployment:
    app_name: str
    modal_environment: str
    package_versions: Mapping[str, str]
    resource_profile: WorkerResourceProfile

    def __post_init__(self) -> None:
        if not isinstance(self.app_name, str) or not self.app_name:
            raise ValueError("Modal worker app name must not be empty")
        if (
            not isinstance(self.modal_environment, str)
            or not self.modal_environment
        ):
            raise ValueError("Modal environment must not be empty")
        if not isinstance(self.resource_profile, WorkerResourceProfile):
            raise TypeError(
                "Modal worker resource profile must be a WorkerResourceProfile"
            )
        if not isinstance(self.package_versions, Mapping):
            raise TypeError("Package versions must be a mapping")
        if any(
            not isinstance(country, str)
            or not country
            or not isinstance(version, str)
            or not version
            for country, version in self.package_versions.items()
        ):
            raise ValueError(
                "Package versions must map non-empty country identifiers "
                "to non-empty version strings"
            )
        object.__setattr__(
            self,
            "package_versions",
            MappingProxyType(dict(self.package_versions)),
        )


def parse_package_versions_json(raw_value: str) -> dict[str, str]:
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Package versions must be encoded as a JSON object"
        ) from exc
    if not isinstance(parsed, dict):
        raise ValueError("Package versions must be encoded as a JSON object")

    invalid = [
        country
        for country, version in parsed.items()
        if not isinstance(country, str)
        or not country
        or not isinstance(version, str)
        or not version
    ]
    if invalid:
        raise ValueError(
            "Package versions must map non-empty country identifiers to "
            "non-empty version strings"
        )
    return dict(parsed)
