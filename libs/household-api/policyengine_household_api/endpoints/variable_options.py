from flask import jsonify, request

from policyengine_household_api.country import COUNTRIES


def get_variable_options(variable: str):
    variables = COUNTRIES["us"].tax_benefit_system.variables
    definition = variables.get(variable)
    territories = (
        (definition.metadata or {}).get("states_by_value")
        if definition
        else None
    )
    if territories is None:
        return jsonify(
            status="error",
            message=f"State-filtered options for {variable} are unavailable in this model version.",
        ), 404

    state = request.args.get("state", "").strip().upper()
    if state not in variables["state_code"].possible_values.__members__:
        return jsonify(
            status="error", message="Supply a valid US state code in state."
        ), 400

    options = [
        {"value": choice.name, "label": choice.value}
        for choice in definition.possible_values
        if choice.name in territories
        and (
            territories[choice.name] is None
            or state in territories[choice.name]
        )
    ]
    return jsonify(status="ok", result=options)
