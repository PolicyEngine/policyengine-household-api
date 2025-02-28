from policyengine_household_api.models.household import HouseholdModel
from typing import Literal, Any, Optional
from pydantic import BaseModel
from dataclasses import dataclass

# Ignore these variables when flattening; they are actually a "role"
# and not directly part of computation
VARIABLE_BLACKLIST = ["members"]


class FlattenedVariable(BaseModel):
    entity_group: str
    entity: str
    variable: str
    year: int
    value: Any


@dataclass
class FlattenedVariableFilter:
    filter_on: Literal["entity_group", "entity", "variable", "year", "value"]
    desired_value: Any


def flatten_variables_from_household(
    household: HouseholdModel,
    filter: Optional[FlattenedVariableFilter] = None,
    max_allowed: Optional[int] = None,
) -> list[FlattenedVariable]:
    """
    Parse variable from a household and raise error if
    more than one is provided.
    Args:
        household (dict): The household.
    Returns:
        list[FlattenedVariable]: List of all variables flattened from household.
    """

    flattened_variables = []

    for entity_group in household.keys():
        for entity in household[entity_group].keys():
            for variable in household[entity_group][entity].keys():
                if variable in VARIABLE_BLACKLIST:
                    continue
                for year in household[entity_group][entity][variable].keys():
                    new_pair = FlattenedVariable.model_validate(
                        {
                            "entity_group": entity_group,
                            "entity": entity,
                            "variable": variable,
                            "year": int(year),
                            "value": household_dict[entity_group][entity][
                                variable
                            ][year],
                        }
                    )

                flattened_variables.append(new_pair)

    if filter:
        flattened_variables = filter_flattened_variables(
            flattened_variables,
            filter_on=filter.filter_on,
            desired_value=filter.desired_value,
        )

    if max_allowed and len(flattened_variables) > max_allowed:
        raise ValueError(
            f"More than {max_allowed} variable(s) was/were provided: {flattened_variables}"
        )

    return flattened_variables


def filter_flattened_variables(
    flattened_variables: list[FlattenedVariable],
    filter_on: Literal["entity_group", "entity", "variable", "year", "value"],
    desired_value: Any,
) -> list[FlattenedVariable]:
    """
    Filter parsed variables by a key-value pair.
    Args:
        flattened_variables (list[FlattenedVariable]): The parsed variables.
        key (Literal["entity_group", "entity", "variable", "year"]): The key to filter by.
        value (Any): The value to filter by.
    Returns:
        list[FlattenedVariable]: The filtered parsed variables.
    """
    return [
        flattened_variable
        for flattened_variable in flattened_variables
        if getattr(flattened_variable, filter_on) == desired_value
    ]
