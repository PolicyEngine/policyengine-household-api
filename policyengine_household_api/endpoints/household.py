import json
from flask import Response, request
from uuid import UUID
from policyengine_household_api.country import COUNTRIES
from policyengine_household_api.utils.validate_country import validate_country
import json
import logging


@validate_country
def get_calculate(country_id: str, add_missing: bool = False) -> Response:
    """Lightweight endpoint for passing in household JSON objects and calculating without storing data.

    Args:
        country_id (str): The country ID.
        add_missing (bool = False): Whether or not to populate all
            possible variables into the household object; this is a special
            use case and should usually be kept at its default setting.
    """

    payload = request.json
    household_json = payload.get("household", {})
    policy_json = payload.get("policy", {})
    enable_ai_explainer = payload.get("enable_ai_explainer", False)

    country = COUNTRIES.get(country_id)

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
    )

    if enable_ai_explainer:
        response_body["computation_tree_uuid"] = str(computation_tree_uuid)

    return Response(
        json.dumps(
            response_body,
        ),
        200,
        mimetype="application/json",
    )
