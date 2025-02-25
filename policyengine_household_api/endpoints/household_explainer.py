import json
import logging
from flask import request, Response, stream_with_context
from typing import Generator, Any
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
from pydantic import ValidationError
from werkzeug.exceptions import BadRequest


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
        payload: dict[str, Any] = request.json

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
        # except Exception as e:
        #     logging.exception(e)
        #     return Response(
        #         json.dumps(
        #             dict(
        #                 status="error",
        #                 message=f"Error validating household data: {e}",
        #             )
        #         ),
        #         status=400,
        #         mimetype="application/json",
        #     )

        # We currently only allow one variable at a time due to
        # challenges calculating billing for multiple
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
        storage_manager = GoogleCloudStorageManager()
        computation_tree: ComputationTree = storage_manager.get(
            uuid=uuid, deserializer=ComputationTree
        )

        # Break ComputationTree into relevant elements
        full_tree = computation_tree.tree
        entity_description = computation_tree.entity_description

        # except Exception as e:
        #     logging.exception(e)
        #     return Response(
        #         json.dumps(
        #             dict(
        #                 status="error",
        #                 message=f"Error fetching tracer data: {e}",
        #             )
        #         ),
        #         status=500,
        #         mimetype="application/json",
        #     )

        # Parse the tracer for the calculation tree of the variable
        variable = flattened_var.variable
        entity = flattened_var.entity
        computation_tree_segment: list[str] = (
            parse_computation_tree_for_variable(
                variable=variable, tree=full_tree
            )
        )
        # except Exception as e:
        #     logging.exception(e)
        #     return Response(
        #         json.dumps(
        #             dict(
        #                 status="error",
        #                 message=f"Error parsing tracer output: {e}",
        #             )
        #         ),
        #         status=500,
        #         mimetype="application/json",
        #     )

        # Modify the computation tree to include data on entity groups
        computation_tree_segment = add_entity_groups_to_computation_tree(
            country_id, computation_tree_segment, entity_description
        )
        # except Exception as e:
        #     logging.exception(e)
        #     return Response(
        #         json.dumps(
        #             dict(
        #                 status="error",
        #                 message=f"Error injecting entity groups into computation tree: {e}",
        #             )
        #         ),
        #         status=500,
        #         mimetype="application/json",
        #     )

        # Generate the AI explainer prompt using the variable calculation tree
        prompt = household_explainer_template.format(
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

    except FileNotFoundError as e:
        logging.exception(e)
        return Response(
            json.dumps(
                dict(
                    status="error",
                    message=f"Unable to find record with UUID {uuid}",
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
