"""Validate household variable names before building a simulation."""

from dataclasses import dataclass

from policyengine_household_api.utils.deprecated_inputs import (
    DEPRECATED_VARIABLES,
)
from policyengine_household_api.utils.household import VARIABLE_BLACKLIST


@dataclass(frozen=True)
class HouseholdVariableValidationError:
    """An unavailable variable name was supplied in a household payload."""

    variable: str
    entity_plural: str
    entity_id: str
    model_version: str | None = None

    @property
    def location(self) -> str:
        if self.entity_plural == "axes":
            return f"`axes[{self.entity_id}].name`"
        return f"`{self.entity_plural}/{self.entity_id}`"

    @property
    def message(self) -> str:
        version = (
            f"PolicyEngine model version {self.model_version}"
            if self.model_version
            else "the current PolicyEngine model version"
        )
        return (
            f"Variable `{self.variable}` on {self.location} is not available "
            f"in {version} "
            f"used by this API. Remove it or migrate to a supported variable."
        )


def validate_household_variables(
    household: dict,
    system,
    model_version: str | None = None,
) -> list[HouseholdVariableValidationError]:
    """Return unavailable variable names found in ``household``.

    A variable is accepted when it exists in the active tax-benefit
    system or is explicitly listed in the deprecated-variable allowlist.
    Deprecated variables are filtered out later with a warning.
    """
    if not isinstance(household, dict):
        return []

    errors: list[HouseholdVariableValidationError] = []

    for entity_plural, entity_group in household.items():
        if entity_plural == "axes" or not isinstance(entity_group, dict):
            continue
        for entity_id, variables in entity_group.items():
            if not isinstance(variables, dict):
                continue
            for variable_name, period_map in variables.items():
                if variable_name in VARIABLE_BLACKLIST:
                    continue
                if not isinstance(period_map, dict):
                    continue
                if _is_available_variable(variable_name, system):
                    continue
                errors.append(
                    HouseholdVariableValidationError(
                        variable=variable_name,
                        entity_plural=entity_plural,
                        entity_id=entity_id,
                        model_version=model_version,
                    )
                )

    for location, variable_name in _walk_axis_variable_names(household):
        if _is_available_variable(variable_name, system):
            continue
        errors.append(
            HouseholdVariableValidationError(
                variable=variable_name,
                entity_plural="axes",
                entity_id=location,
                model_version=model_version,
            )
        )

    return errors


def _is_available_variable(variable_name: str, system) -> bool:
    return (
        variable_name in system.variables
        or variable_name in DEPRECATED_VARIABLES
    )


def _walk_axis_variable_names(household: dict):
    axes = household.get("axes")
    if not isinstance(axes, list):
        return

    for entry_index, entry in enumerate(axes):
        if isinstance(entry, list):
            for axis_index, axis in enumerate(entry):
                if not isinstance(axis, dict):
                    continue
                variable_name = axis.get("name")
                if variable_name is None:
                    continue
                yield f"{entry_index}][{axis_index}", variable_name
            continue

        if not isinstance(entry, dict):
            continue
        variable_name = entry.get("name")
        if variable_name is None:
            continue
        yield str(entry_index), variable_name
