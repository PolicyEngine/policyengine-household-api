import json
import logging
from flask import request, Response, stream_with_context
from typing import Generator
from policyengine_household_api.models.computation_tree import ComputationTree
from policyengine_household_api.utils.validate_country import validate_country
from policyengine_household_api.utils.tracer import (
    trigger_buffered_ai_analysis,
    trigger_streaming_ai_analysis,
    prompt_template,
)


@validate_country
def get_ai_explainer(country_id: str) -> Response:
    """
    Generate an AI explainer output for a given variable in
    a particular household.

    Args:
        country_id (str): The country ID.

    Returns:
        Response: The AI explainer output or an error.
    """

    # Pull the UUID and variable from the query parameters
    computation_tree_uuid: str = request.args.get("computation_tree_uuid")
    variable: str = request.args.get("variable")
    use_streaming: bool = request.args.get("use_streaming", False)

    # Fetch the tracer output from the Google Cloud bucket
    try:
        computation_tree_data: ComputationTree = ComputationTree(
            country_id, computation_tree_uuid=computation_tree_uuid
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
    try:
        computation_tree_segment: list[str] = (
            computation_tree_data.parse_computation_tree_output(variable)
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
