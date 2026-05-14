from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re
from typing import Any

import yaml


CONFIG_KEY = "modal_release"
REQUIRED_CONFIG_KEYS = {
    "new_app_target",
    "promote_existing_frontier",
    "cleanup_target",
}
MODAL_RELEASE_PATH_PREFIXES = (
    ".github/scripts/modal",
    ".github/scripts/check_modal_release_",
    ".github/scripts/resolve_modal_release_config.py",
    ".github/scripts/run-deployed-tests-for-modal-channels.sh",
    ".github/workflows/deploy-staged.yml",
    ".github/PULL_REQUEST_TEMPLATE.md",
    "docs/engineering/skills/modal-release-prs.md",
    "policyengine_household_api/modal_release/",
)


class ModalReleaseConfigError(ValueError):
    """Raised when a Modal release configuration is missing or invalid."""


class NewAppTarget(StrEnum):
    FRONTIER = "frontier"
    CURRENT = "current"
    NONE = "none"


class CleanupTarget(StrEnum):
    NONE = "none"
    RETIRED = "retired"
    FRONTIER = "frontier"
    CURRENT = "current"


@dataclass(frozen=True)
class ModalReleaseConfig:
    new_app_target: NewAppTarget
    promote_existing_frontier: bool
    cleanup_target: CleanupTarget

    @property
    def deploys_new_app(self) -> bool:
        return self.new_app_target != NewAppTarget.NONE

    @classmethod
    def from_mapping(
        cls,
        config: dict[str, Any],
        *,
        allow_active_cleanup: bool = False,
    ) -> "ModalReleaseConfig":
        _validate_config_keys(config)

        new_app_target = _enum_value(
            NewAppTarget,
            config["new_app_target"],
            "new_app_target",
        )
        cleanup_target = _enum_value(
            CleanupTarget,
            config["cleanup_target"],
            "cleanup_target",
        )
        promote_existing_frontier = config["promote_existing_frontier"]
        if not isinstance(promote_existing_frontier, bool):
            raise ModalReleaseConfigError(
                "`promote_existing_frontier` must be true or false"
            )

        parsed = cls(
            new_app_target=new_app_target,
            promote_existing_frontier=promote_existing_frontier,
            cleanup_target=cleanup_target,
        )
        parsed.validate(allow_active_cleanup=allow_active_cleanup)
        return parsed

    def validate(self, *, allow_active_cleanup: bool = False) -> None:
        if (
            self.promote_existing_frontier
            and self.new_app_target != NewAppTarget.FRONTIER
        ):
            raise ModalReleaseConfigError(
                "`promote_existing_frontier` may only be true when "
                "`new_app_target` is `frontier`"
            )

        if (
            self.cleanup_target
            in {CleanupTarget.CURRENT, CleanupTarget.FRONTIER}
            and not allow_active_cleanup
        ):
            raise ModalReleaseConfigError(
                "`cleanup_target` may not be `current` or `frontier` "
                "in pull request configuration"
            )


def default_weekly_config() -> ModalReleaseConfig:
    return ModalReleaseConfig(
        new_app_target=NewAppTarget.FRONTIER,
        promote_existing_frontier=True,
        cleanup_target=CleanupTarget.NONE,
    )


def parse_modal_release_config_from_body(
    body: str | None,
    *,
    allow_active_cleanup: bool = False,
) -> ModalReleaseConfig:
    mapping = extract_modal_release_config(body)
    return ModalReleaseConfig.from_mapping(
        mapping,
        allow_active_cleanup=allow_active_cleanup,
    )


def body_contains_modal_release_config(body: str | None) -> bool:
    return bool(
        body
        and any(CONFIG_KEY in block for block in _candidate_yaml_blocks(body))
    )


def extract_modal_release_config(body: str | None) -> dict[str, Any]:
    if not body:
        raise ModalReleaseConfigError(
            "PR body must include a `modal_release` YAML block"
        )

    for candidate in _candidate_yaml_blocks(body):
        if CONFIG_KEY not in candidate:
            continue
        try:
            parsed_documents = [
                document
                for document in yaml.safe_load_all(candidate)
                if document is not None
            ]
        except yaml.YAMLError as e:
            raise ModalReleaseConfigError(
                f"PR body contains invalid `modal_release` YAML: {e}"
            ) from e

        for document in parsed_documents:
            if isinstance(document, dict) and CONFIG_KEY in document:
                config = document[CONFIG_KEY]
                if not isinstance(config, dict):
                    raise ModalReleaseConfigError(
                        "`modal_release` must be a YAML mapping"
                    )
                return config

    raise ModalReleaseConfigError(
        "PR body must include a `modal_release` YAML block"
    )


def release_config_to_dict(config: ModalReleaseConfig) -> dict[str, Any]:
    return {
        "new_app_target": config.new_app_target.value,
        "promote_existing_frontier": config.promote_existing_frontier,
        "cleanup_target": config.cleanup_target.value,
    }


def changed_files_require_modal_release_config(
    filenames: list[str],
) -> bool:
    return any(
        filename.startswith(prefix)
        for filename in filenames
        for prefix in MODAL_RELEASE_PATH_PREFIXES
    )


def _candidate_yaml_blocks(body: str) -> list[str]:
    fenced_blocks = [
        match.group("body")
        for match in re.finditer(
            r"```ya?ml\s*\n(?P<body>.*?)\n```",
            body,
            flags=re.DOTALL | re.IGNORECASE,
        )
    ]
    stripped_body = body.strip()
    if stripped_body.startswith(f"{CONFIG_KEY}:"):
        return fenced_blocks + [body]
    return fenced_blocks


def _validate_config_keys(config: dict[str, Any]) -> None:
    config_keys = set(config)
    missing = REQUIRED_CONFIG_KEYS - config_keys
    extra = config_keys - REQUIRED_CONFIG_KEYS

    if missing:
        keys = ", ".join(sorted(missing))
        raise ModalReleaseConfigError(
            f"`modal_release` is missing required key(s): {keys}"
        )
    if extra:
        keys = ", ".join(sorted(extra))
        raise ModalReleaseConfigError(
            f"`modal_release` contains unsupported key(s): {keys}"
        )


def _enum_value(
    enum_type: type[NewAppTarget] | type[CleanupTarget],
    value: Any,
    key: str,
) -> NewAppTarget | CleanupTarget:
    if not isinstance(value, str):
        raise ModalReleaseConfigError(f"`{key}` must be a string")

    try:
        return enum_type(value)
    except ValueError as e:
        valid_values = ", ".join(option.value for option in enum_type)
        raise ModalReleaseConfigError(
            f"`{key}` must be one of: {valid_values}"
        ) from e
