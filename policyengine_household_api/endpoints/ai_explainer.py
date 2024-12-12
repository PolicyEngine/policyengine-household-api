import json
import logging
from flask import request, Response, stream_with_context
from typing import Generator
from policyengine_household_api.utils.validate_country import validate_country
from policyengine_household_api.utils.google_cloud import (
    fetch_from_cloud_bucket,
)
from policyengine_household_api.utils.tracer import (
    parse_tracer_output,
    trigger_ai_analysis,
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
    uuid: str = request.args.get("uuid")
    variable: str = request.args.get("variable")

    # Fetch the tracer output from the Google Cloud bucket
    try:
        tracer_data: dict = fetch_from_cloud_bucket(uuid)
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
        complete_tracer = tracer_data["tracer"]
        tracer_segment: list[str] = parse_tracer_output(
            complete_tracer, variable
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
            variable=variable, tracer_segment=tracer_segment
        )

        # Pass all of this to Claude
        analysis: Generator = trigger_ai_analysis(prompt)
        return Response(
            stream_with_context(analysis),
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
