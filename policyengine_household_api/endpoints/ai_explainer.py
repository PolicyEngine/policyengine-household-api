import json
from flask import request, Response
from policyengine_household_api.utils.validate_country import validate_country
from policyengine_household_api.utils.google_cloud import fetch_from_cloud_bucket
from policyengine_household_api.utils.tracer import parse_tracer_output


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
        print(f"Error parsing tracer output: {str(e)}")
        raise e

    # Generate the AI explainer prompt using the variable calculation tree

    # Pass all of this to Claude

    # Return Claude's output
