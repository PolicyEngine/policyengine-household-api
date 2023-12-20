from policyengine_api_light.country import (
    COUNTRIES,
    validate_country,
)
import json
from flask import Response, request
from policyengine_api_light.country import COUNTRIES
import json
import logging


def add_yearly_variables(household, country_id):
    """
    Add yearly variables to a household dict before enqueueing calculation
    """
    metadata = COUNTRIES.get(country_id).metadata["result"]

    variables = metadata["variables"]
    entities = metadata["entities"]

    for variable in variables:
        if variables[variable]["definitionPeriod"] in (
            "year",
            "month",
            "eternity",
        ):
            entity_plural = entities[variables[variable]["entity"]]["plural"]
            if entity_plural in household:
                possible_entities = household[entity_plural].keys()
                for entity in possible_entities:
                    if (
                        not variables[variable]["name"]
                        in household[entity_plural][entity]
                    ):
                        if variables[variable]["isInputVariable"]:
                            household[entity_plural][entity][
                                variables[variable]["name"]
                            ] = {2023: variables[variable]["defaultValue"]}
                        else:
                            household[entity_plural][entity][
                                variables[variable]["name"]
                            ] = {2023: None}
    return household


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

    if add_missing:
        # Add in any missing yearly variables to household_json
        household_json = add_yearly_variables(household_json, country_id)

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
