import json
import logging
import os
from flask import request, Response, stream_with_context
from typing import Any, Optional, Tuple
from policyengine_household_api.models import (
    HouseholdModelUS,
    HouseholdModelUK,
    HouseholdModelGeneric,
    ComputationTree,
)
from policyengine_household_api.utils.google_cloud import (
    GoogleCloudStorageManager,
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
    parse_computation_tree_for_variable,
    add_entity_groups_to_computation_tree,
)
from policyengine_household_api.ai_templates import (
    household_explainer_template,
)
from policyengine_household_api.utils.config_loader import get_config_value
from pydantic import ValidationError


def _check_anthropic_configuration() -> Tuple[bool, Optional[str]]:
    """
    Check if Anthropic API is properly configured.

    Returns:
        Tuple[bool, Optional[str]]: (is_configured, api_key)
            - is_configured: True if AI services are enabled and API key is present
            - api_key: The API key if configured, None otherwise
    """
    # Check configuration
    ai_enabled = bool(get_config_value("ai.enabled", False))
    api_key = get_config_value("ai.anthropic.api_key", "")

    # Backward compatibility: auto-enable if ANTHROPIC_API_KEY env var is set
    if not ai_enabled and not api_key:
        env_api_key = os.getenv("ANTHROPIC_API_KEY")
        if env_api_key:
            api_key = env_api_key
            ai_enabled = True

    # Convert empty string to None for clarity
    if not api_key:
        api_key = None

    return (ai_enabled and api_key is not None), api_key


def _create_unauthorized_response() -> Response:
    """
    Create a 401 response for missing Anthropic configuration.

    Returns:
        Response: A 401 Unauthorized response with error details.
    """
    return Response(
        json.dumps(
            dict(
                status="error",
                message="Anthropic API key is not configured. Please contact your administrator to enable AI features.",
            )
        ),
        status=401,
        mimetype="application/json",
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

    try:
        # Check if AI services are properly configured
        is_configured, api_key = _check_anthropic_configuration()

        if not is_configured or api_key is None:
            return _create_unauthorized_response()

        # api_key is guaranteed to be non-None here due to is_configured check

        payload: dict[str, Any] = request.json

        # Pull the UUID from the query parameters
        uuid: Optional[str] = payload.get("computation_tree_uuid")
        if not uuid:
            return Response(
                json.dumps(
                    dict(
                        status="error",
                        message="computation_tree_uuid is required",
                    )
                ),
                status=400,
                mimetype="application/json",
            )

        use_streaming: bool = payload.get("use_streaming", False)

        household_raw = payload.get("household")

        # Parse household based on country
        household = None
        if country_id == "us":
            household = HouseholdModelUS.model_validate(household_raw)
        elif country_id == "uk":
            household = HouseholdModelUK.model_validate(household_raw)
        else:
            household = HouseholdModelGeneric.model_validate(household_raw)

        # Filter the flattened household and look for one (and only one)
        # variable whose "value" equals "None"
        # We currently only allow one variable at a time due to
        # challenges calculating billing for multiple
        temporary_single_explainer_filter = FlattenedVariableFilter(
            filter_on="value", desired_value=None
        )
        flattened_var_list: list[FlattenedVariable] = (
            flatten_variables_from_household(
                household,
                filter=temporary_single_explainer_filter,
                max_allowed=1,
            )
        )

        if len(flattened_var_list) == 0:
            return Response(
                json.dumps(
                    dict(
                        status="error",
                        message="Household must include at least one variable set to null",
                    )
                ),
                status=400,
                mimetype="application/json",
            )

        # Fetch the tracer output from the Google Cloud bucket
        flattened_var = flattened_var_list[0]
        storage_manager = GoogleCloudStorageManager()

        # Convert string UUID to proper type for storage manager
        from uuid import UUID

        computation_tree: ComputationTree = storage_manager.get(
            uuid=UUID(uuid), deserializer=ComputationTree
        )

        # Break ComputationTree into relevant elements
        full_tree = computation_tree.tree
        entity_description = computation_tree.entity_description

        # Parse the tracer for the calculation tree of the variable
        variable = flattened_var.variable
        entity = flattened_var.entity
        computation_tree_segment: list[str] = (
            parse_computation_tree_for_variable(
                variable=variable, tree=full_tree
            )
        )

        # Computation trees do not include entity names, only
        # vectorized outputs, so e.g., for person-level vars in a household
        # of 4, the tree has 4 values. We want the LLM to equate each
        # var with its entity, then apply the entity_description we pass it
        # to know who's who. Add the entity groups to the tree.
        computation_tree_segment = add_entity_groups_to_computation_tree(
            country_id, computation_tree_segment, entity_description
        )

        # Generate the AI explainer prompt using the variable calculation tree
        prompt = household_explainer_template.format(
            variable=variable,
            computation_tree_segment=computation_tree_segment,
            entity_description=entity_description.model_dump(),
            entity=entity,
        )

        # Pass all of this to Claude with the API key
        if use_streaming:
            streaming_analysis = trigger_streaming_ai_analysis(prompt, api_key)
            return Response(
                stream_with_context(streaming_analysis),
                status=200,
            )

        buffered_analysis = trigger_buffered_ai_analysis(prompt, api_key)
        return Response(
            json.dumps({"response": buffered_analysis}),
            status=200,
        )

    except FileNotFoundError as e:
        logging.exception(e)
        return Response(
            json.dumps(
                dict(
                    status="error",
                    message="Unable to find record with specified UUID",
                )
            ),
            status=400,
        )
    except ValidationError as e:
        logging.exception(e)
        return Response(
            json.dumps(
                dict(
                    status="error",
                    message=f"Error validating household data: {e}",
                )
            ),
            status=400,
            mimetype="application/json",
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
