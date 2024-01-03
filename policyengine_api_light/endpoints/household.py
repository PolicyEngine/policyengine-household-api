from policyengine_api_light.country import (
    COUNTRIES,
    validate_country,
)
import json
from flask import Response, request
from policyengine_api_light.country import COUNTRIES
import json
import logging


def get_calculate(country_id: str, add_missing: bool = False) -> dict:
    """Lightweight endpoint for passing in household and policy JSON objects and calculating without storing data.

    Args:
        country_id (str): The country ID.
    """

    country_not_found = validate_country(country_id)
    if country_not_found:
        return country_not_found

    payload = request.json
    household_json = payload.get("household", {})
    policy_json = payload.get("policy", {})

    country = COUNTRIES.get(country_id)

    try:
        result = country.calculate(household_json, policy_json)
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

    return dict(
        status="ok",
        message=None,
        result=result,
    )
