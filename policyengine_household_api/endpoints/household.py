import json
import logging
from flask import Response, request
from pydantic import ValidationError
from uuid import UUID
from policyengine_household_api.country import (
    COUNTRIES,
    detect_period_warnings,
    validate_period_budgets,
)
from policyengine_household_api.models.household import (
    HouseholdModelGeneric,
    HouseholdModelUK,
    HouseholdModelUS,
)
from policyengine_household_api.utils.validate_country import validate_country


# Limits for reform-style "axes" scans. Axes multiply the computation
# cost by count_0 * count_1 * ... for each entry, so uncapped axes can
# be used to DoS the compute pool. Keep these conservative.
MAX_AXES_ENTRIES = 10
MAX_AXES_COUNT = 100


# Per-country household schemas used to validate inbound /calculate
# payloads. The `us` and `uk` models extend the generic base with the
# extra entity groups they allow.
HOUSEHOLD_SCHEMAS = {
    "us": HouseholdModelUS,
    "uk": HouseholdModelUK,
}


def _validate_household_payload(country_id: str, household_json: dict) -> None:
    """Validate a household payload against the country-specific schema.

    Raises ``ValueError`` with a user-safe message on failure.
    """
    if not isinstance(household_json, dict):
        raise ValueError("'household' must be a JSON object")

    # Strip the axes key before running Pydantic; axes are validated
    # separately because they aren't part of the HouseholdModel schema.
    household_for_schema = {
        k: v for k, v in household_json.items() if k != "axes"
    }

    schema_cls = HOUSEHOLD_SCHEMAS.get(country_id, HouseholdModelGeneric)
    try:
        schema_cls.model_validate(household_for_schema)
    except ValidationError as e:
        raise ValueError(f"Invalid household payload: {e}")


def _validate_axes(household_json: dict) -> None:
    """Validate the optional `axes` field's shape and size."""
    axes = household_json.get("axes")
    if axes is None:
        return

    if not isinstance(axes, list):
        raise ValueError("'axes' must be a list")

    if len(axes) > MAX_AXES_ENTRIES:
        raise ValueError(
            f"'axes' may contain at most {MAX_AXES_ENTRIES} entries; "
            f"got {len(axes)}"
        )

    for i, entry in enumerate(axes):
        for axis in _axes_entry_specs(entry, i):
            _validate_axis_count(axis, i)


def _axes_entry_specs(entry, index: int) -> list[dict]:
    # Each entry may itself be a list of axis specifications, which
    # supports nested/crossed scans in policyengine-core.
    axes = entry if isinstance(entry, list) else [entry]
    for axis in axes:
        if not isinstance(axis, dict):
            raise ValueError(
                f"'axes[{index}]' must be an object or list of objects"
            )
    return axes


def _validate_axis_count(axis: dict, index: int) -> None:
    count = axis.get("count")
    if count is None:
        return

    count_int = _parse_axis_count(count, index)
    if count_int < 1 or count_int > MAX_AXES_COUNT:
        raise ValueError(
            f"'axes[{index}].count' must be between 1 and "
            f"{MAX_AXES_COUNT}; got {count_int}"
        )


def _parse_axis_count(count, index: int) -> int:
    try:
        return int(count)
    except (TypeError, ValueError):
        raise ValueError(f"'axes[{index}].count' must be an integer")


@validate_country
def get_calculate(country_id: str, add_missing: bool = False) -> Response:
    """Lightweight endpoint for passing in household JSON objects and calculating without storing data.

    Args:
        country_id (str): The country ID.
        add_missing (bool = False): Whether or not to populate all
            possible variables into the household object; this is a special
            use case and should usually be kept at its default setting.
    """

    payload = request.json or {}
    household_json = payload.get("household", {})
    policy_json = payload.get("policy", {})
    enable_ai_explainer = payload.get("enable_ai_explainer", False)

    country = COUNTRIES.get(country_id)

    # Validate inbound payload shape before reaching the compute layer.
    try:
        _validate_household_payload(country_id, household_json)
        _validate_axes(household_json)
        validate_period_budgets(household_json, country.tax_benefit_system)
    except ValueError as e:
        return Response(
            json.dumps({"status": "error", "message": str(e)}),
            status=400,
            mimetype="application/json",
        )

    # Detect partial monthly input + annual output combinations so partners
    # see a heads-up that some months will read the engine's fallback. v1
    # has no such warning; this is purely additive diagnostic.
    period_warnings = detect_period_warnings(
        household_json, country.tax_benefit_system
    )

    try:
        result: dict
        computation_tree_uuid: UUID | None
        result, computation_tree_uuid = country.calculate(
            household_json, policy_json, enable_ai_explainer
        )
    except Exception as e:
        logging.exception(e)
        response_body = dict(
            status="error",
            message=f"Error calculating household under policy: {e}",
        )
        return Response(
            json.dumps(response_body),
            status=500,
            mimetype="application/json",
        )

    response_body = dict(
        status="ok",
        message=None,
        result=result,
        policyengine_bundle=dict(country.policyengine_bundle),
    )

    if period_warnings:
        # Serialize to strings on the wire; the structured dataclasses
        # stay available for any future caller that wants the fields.
        response_body["warnings"] = [w.message for w in period_warnings]

    if enable_ai_explainer:
        response_body["computation_tree_uuid"] = str(computation_tree_uuid)

    return Response(
        json.dumps(
            response_body,
        ),
        200,
        mimetype="application/json",
    )
