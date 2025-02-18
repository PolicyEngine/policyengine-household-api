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

    # Pull the UUID from the query parameters
    uuid: str = payload.get("computation_tree_uuid")
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
    flattened_var_list: list[FlattenedVariable] = (
        flatten_variables_from_household(
            household, filter=temporary_single_explainer_filter, limit=1
        )
    )

    if len(flattened_var_list) == 0:
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
    flattened_var = flattened_var_list[0]
    try:
        computation_tree = ComputationTree()
        full_tree, entity_description = computation_tree.get_computation_tree(
            uuid=uuid
        )
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
    entity = flattened_var.entity
    try:
        computation_tree_segment: list[str] = (
            computation_tree.parse_computation_tree_for_variable(
                variable=variable
            )
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
            entity_description=entity_description.model_dump(),
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
