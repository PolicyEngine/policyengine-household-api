from policyengine_household_api.models.household import HouseholdModel
from typing import Literal, Any
from pydantic import BaseModel
from dataclasses import dataclass

# Don't consider these variables due to their unique nature
VARIABLE_BLACKLIST = ["members"]


class FlattenedVariable(BaseModel):
    entity_group: str
    entity: str
    variable: str
    year: int
    value: Any


@dataclass
class FlattenedVariableFilter:
    key: Literal["entity_group", "entity", "variable", "year", "value"]
    value: Any


def flatten_variables_from_household(
    household: HouseholdModel,
    filter: FlattenedVariableFilter | None,
    limit: int | None,
) -> list[FlattenedVariable]:
    """
    Parse variable from a household and raise error if
    more than one is provided.

    Args:
        household (HouseholdModel): The household model.

    Returns:
        tuple[str, str]: The variable and entity.
    """

    household_dict = household.model_dump()
    flattened_variables = []

    for entity_group in household_dict.keys():
        for entity in household_dict[entity_group].keys():
            for variable in household_dict[entity_group][entity].keys():
                if variable in VARIABLE_BLACKLIST:
                    continue
                for year in household_dict[entity_group][entity][
                    variable
                ].keys():
                    new_pair = FlattenedVariable.model_validate(
                        {
                            "entity_group": entity_group,
                            "entity": entity,
                            "variable": variable,
                            "year": year,
                            "value": household_dict[entity_group][entity][
                                variable
                            ][year],
                        }
                    )

                flattened_variables.append(new_pair)

    if filter:
        flattened_variables = filter_flattened_variables(
            flattened_variables, filter.key, filter.value
        )

    if limit and len(flattened_variables) > limit:
        raise ValueError(
            f"More than {limit} variable(s) was/were provided: {flattened_variables}"
        )

    return flattened_variables


def filter_flattened_variables(
    flattened_variables: list[FlattenedVariable],
    key: Literal["entity_group", "entity", "variable", "year", "value"],
    value: Any,
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
        if getattr(flattened_variable, key) == value
    ]
