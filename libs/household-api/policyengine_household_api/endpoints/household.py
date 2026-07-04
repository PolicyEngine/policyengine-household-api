import json
import logging
from flask import Response, request
from policyengine_observability import record_error
from policyengine_observability import segment
from policyengine_observability import set_attribute
from pydantic import ValidationError
from policyengine_household_api.country import (
    COUNTRIES,
    detect_period_warnings,
    validate_period_budgets,
    validate_period_keys,
)
from policyengine_household_common.models.household import (
    HouseholdModelGeneric,
    HouseholdModelUK,
    HouseholdModelUS,
)
from policyengine_household_common.observability.segments import SegmentName
from policyengine_household_common.deprecated_inputs import (
    drop_deprecated_inputs,
)
from policyengine_household_api.utils.variable_validation import (
    validate_household_variables,
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
            _validate_axis_name(axis, i)
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


def _validate_axis_name(axis: dict, index: int) -> None:
    name = axis.get("name")
    if not isinstance(name, str) or name == "":
        raise ValueError(f"'axes[{index}].name' must be a non-empty string")


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

    set_attribute("country_id", country_id)

    with segment(SegmentName.REQUEST_PARSE):
        payload = request.json or {}
        household_json = payload.get("household", {})
        policy_json = payload.get("policy", {})

    country = COUNTRIES.get(country_id)
    set_attribute(
        "model_version",
        country.policyengine_bundle.get("model_version"),
    )

    # Validate inbound payload shape before reaching the compute layer.
    try:
        with segment(SegmentName.PAYLOAD_VALIDATION):
            _validate_household_payload(country_id, household_json)
            _validate_axes(household_json)
    except ValueError as e:
        record_error(e, handled=True, status_code=400, include_stack=False)
        return _json_response(
            {"status": "error", "message": str(e)},
            status=400,
        )

    with segment(SegmentName.VARIABLE_VALIDATION):
        variable_errors = validate_household_variables(
            household=household_json,
            system=country.tax_benefit_system,
            model_version=country.policyengine_bundle["model_version"],
        )
    if variable_errors:
        set_attribute("variable_error_count", len(variable_errors))
        record_error(
            ValueError("Invalid household variables."),
            handled=True,
            status_code=400,
            include_stack=False,
        )
        return _json_response(
            {
                "status": "error",
                "message": "Invalid household variables.",
                "errors": [error.message for error in variable_errors],
            },
            status=400,
        )

    # Strip deprecated inputs from a copy before period validation so
    # partners who still pass removed/renamed variables get a warning +
    # working response instead of a `VariableNotFoundError` HTTP 500.
    with segment(SegmentName.DEPRECATED_INPUT_FILTER):
        deprecated_inputs = drop_deprecated_inputs(household_json)
    household_json = deprecated_inputs.household
    deprecation_warnings = deprecated_inputs.warnings
    set_attribute(
        "deprecated_warning_count",
        len(deprecation_warnings),
    )

    # Validate inbound period data before reaching the compute layer.
    try:
        with segment(SegmentName.PERIOD_VALIDATION):
            validate_period_keys(household_json, country.tax_benefit_system)
            validate_period_budgets(
                household_json,
                country.tax_benefit_system,
            )
    except ValueError as e:
        record_error(e, handled=True, status_code=400, include_stack=False)
        return _json_response(
            {"status": "error", "message": str(e)},
            status=400,
        )

    # Detect partial monthly input + annual output combinations so partners
    # see a heads-up that some months will read the engine's fallback. v1
    # has no such warning; this is purely additive diagnostic.
    with segment(SegmentName.PERIOD_WARNING_DETECTION):
        period_warnings = detect_period_warnings(
            household_json,
            country.tax_benefit_system,
        )
    set_attribute("period_warning_count", len(period_warnings))

    try:
        result: dict
        with segment(SegmentName.CALCULATION):
            result = country.calculate(household_json, policy_json)
    except Exception as e:
        logging.exception(e)
        record_error(e, handled=True, status_code=500)
        response_body = dict(
            status="error",
            message=f"Error calculating household under policy: {e}",
        )
        return _json_response(
            response_body,
            status=500,
        )

    response_body = dict(
        status="ok",
        message=None,
        result=result,
        policyengine_bundle=dict(country.policyengine_bundle),
    )

    warning_messages = [w.message for w in deprecation_warnings] + [
        w.message for w in period_warnings
    ]
    if warning_messages:
        # Serialize to strings on the wire; the structured dataclasses
        # stay available for any future caller that wants the fields.
        response_body["warnings"] = warning_messages

    return _json_response(response_body, status=200)


def _json_response(payload: dict, *, status: int) -> Response:
    with segment(SegmentName.RESPONSE_SERIALIZATION):
        body = json.dumps(payload)
    return Response(body, status, mimetype="application/json")
