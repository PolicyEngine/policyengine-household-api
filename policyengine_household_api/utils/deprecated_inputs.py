"""Detect and drop deprecated input variables before they reach the engine.

Without this, a partner who passes a removed model variable (e.g.
``medical_out_of_pocket_expenses``, deleted in policyengine-us 1.673.0)
crashes the simulation with ``VariableNotFoundError`` (HTTP 500). Dropping
the input and surfacing a structured warning gives partners a soft
landing — every other output computes normally; only outputs that
depended on the deprecated input fall back to defaults.
"""

from dataclasses import dataclass


# Registry of removed/renamed model variables that legacy partner traffic
# may still pass. The value is a one-line migration hint surfaced verbatim
# in the warning message — keep it actionable.
DEPRECATED_VARIABLES: dict[str, str] = {
    "medical_out_of_pocket_expenses": (
        "Removed in policyengine-us 1.673.0. Migrate non-premium spending "
        "to `other_medical_expenses` and premium spending to "
        "`health_insurance_premiums`."
    ),
}


@dataclass(frozen=True)
class DeprecatedVariableWarning:
    """A removed/renamed variable was supplied; dropped before the engine ran."""

    variable: str
    entity_plural: str
    entity_id: str
    hint: str

    @property
    def message(self) -> str:
        return (
            f"Input `{self.variable}` on "
            f"`{self.entity_plural}/{self.entity_id}` is deprecated and was "
            f"ignored for this calculation. {self.hint}"
        )


def drop_deprecated_inputs(
    household: dict,
) -> list[DeprecatedVariableWarning]:
    """Strip deprecated input keys from ``household`` in place.

    Returns one warning per (entity, deprecated-key) occurrence. Mutates
    ``household`` so downstream validation and the simulation never see
    the deprecated keys.

    Non-dict inputs are returned unchanged with no warnings; the
    Pydantic schema check that runs immediately after will reject the
    bad shape with a 400.
    """
    warnings: list[DeprecatedVariableWarning] = []

    if not isinstance(household, dict):
        return warnings

    for entity_plural, entity_group in household.items():
        if not isinstance(entity_group, dict):
            continue
        for entity_id, variables in entity_group.items():
            if not isinstance(variables, dict):
                continue
            for variable_name in list(variables.keys()):
                hint = DEPRECATED_VARIABLES.get(variable_name)
                if hint is None:
                    continue
                warnings.append(
                    DeprecatedVariableWarning(
                        variable=variable_name,
                        entity_plural=entity_plural,
                        entity_id=entity_id,
                        hint=hint,
                    )
                )
                del variables[variable_name]

    return warnings
