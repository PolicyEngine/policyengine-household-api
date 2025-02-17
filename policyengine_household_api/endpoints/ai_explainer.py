import json
import logging
from uuid import UUID
from flask import request, Response, stream_with_context
from typing import Generator
from pydantic import BaseModel
from policyengine_household_api.models.computation_tree import (
    ComputationTree,
    EntityDescription,
)
from policyengine_household_api.models.household import (
    HouseholdModelUS,
    HouseholdModelUK,
    HouseholdModelGeneric,
)
from policyengine_household_api.utils.validate_country import validate_country
from policyengine_household_api.utils.household import (
    flatten_variables_from_household,
    filter_flattened_variables,
    FlattenedVariable,
    FlattenedVariableFilter,
)
from policyengine_household_api.utils.computation_tree import (
    trigger_buffered_ai_analysis,
    trigger_streaming_ai_analysis,
    prompt_template,
)


@validate_country
def generate_ai_explainer(country_id: str) -> Response:
    """
    Generate an AI explainer output for a given variable in
    a particular household.

    Args:
        country_id (str): The country ID.

    Returns:
        Response: The AI explainer output or an error.
    """

    payload = request.json

    # Pull the UUID and variable from the query parameters
    computation_tree_uuid: str = payload.get("computation_tree_uuid")
    use_streaming: bool = payload.get("use_streaming", False)

    household_raw = payload.get("household")
    if country_id == "us":
        household: HouseholdModelUS = HouseholdModelUS.model_validate(
            household_raw
        )
    elif country_id == "uk":
        household: HouseholdModelUK = HouseholdModelUK.model_validate(
            household_raw
        )
    else:
        household: HouseholdModelGeneric = (
            HouseholdModelGeneric.model_validate(household_raw)
        )

    # We currently only allow one variable at a time due to GCP metrics limitations
    temporary_single_explainer_filter = FlattenedVariableFilter(
        key="value", value=None
    )
    flattened_var: FlattenedVariable = flatten_variables_from_household(
        household, filter=temporary_single_explainer_filter, limit=1
    )[0]

    if len(flattened_var) == 0:
        return Response(
            json.dumps(
                dict(
                    status="error",
                    message="No variables found in the household.",
                )
            ),
            status=400,
            mimetype="application/json",
        )

    # Fetch the tracer output from the Google Cloud bucket
    try:
        computation_tree = ComputationTree()
        computation_tree.get_computation_tree(uuid=computation_tree_uuid)
    except Exception as e:
        logging.exception(e)
        return Response(
            json.dumps(
                dict(
                    status="error",
                    message=f"Error fetching tracer data: {e}",
                )
            ),
            status=500,
            mimetype="application/json",
        )

    # Parse the tracer for the calculation tree of the variable
    variable = flattened_var.variable
    year = flattened_var.year
    entity = flattened_var.entity
    try:
        computation_tree_segment: list[str] = (
            computation_tree.parse_computation_tree_for_variable(
                variable=variable
            )
        )
        entity_description = computation_tree.get_entity_description(
            uuid=computation_tree_uuid
        )
    except Exception as e:
        logging.exception(e)
        return Response(
            json.dumps(
                dict(
                    status="error",
                    message=f"Error parsing tracer output: {e}",
                )
            ),
            status=500,
            mimetype="application/json",
        )

    try:
        # Generate the AI explainer prompt using the variable calculation tree
        prompt = prompt_template.format(
            variable=variable,
            computation_tree_segment=computation_tree_segment,
            entity_description=entity_description.to_dict(),
            entity=entity,
        )

        # Pass all of this to Claude
        if use_streaming:
            analysis: Generator = trigger_streaming_ai_analysis(prompt)
            return Response(
                stream_with_context(analysis),
                status=200,
            )

        analysis: str = trigger_buffered_ai_analysis(prompt)
        return Response(
            json.dumps({"response": analysis}),
            status=200,
        )

    except Exception as e:
        logging.exception(e)
        return Response(
            json.dumps(
                dict(
                    status="error",
                    message=f"Error generating tracer analysis result using Claude: {e}",
                )
            ),
            status=500,
            mimetype="application/json",
        )
