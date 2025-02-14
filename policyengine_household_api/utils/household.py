from policyengine_household_api.models.household import HouseholdModel
from pydantic import BaseModel


class ParsedEntityVariablePair(BaseModel):
    entity_group: str
    entity: str
    variable: str


def parse_variables_from_household(
    household: HouseholdModel, limit: int | None = None
) -> list[ParsedEntityVariablePair]:
    """
    Parse variable from a household and raise error if
    more than one is provided.

    Args:
        household (HouseholdModel): The household model.

    Returns:
        tuple[str, str]: The variable and entity.
    """

    household_dict = household.model_dump()
    parsed_variables = []

    for entity_group in household_dict.keys():
        for entity in household_dict[entity_group].keys():
            for variable in household_dict[entity_group][entity].keys():
                parsed_variables.append(
                    ParsedEntityVariablePair(
                        {
                            "entity_group": entity_group,
                            "entity": entity,
                            "variable": variable,
                        }
                    )
                )

    if limit and len(parsed_variables) > limit:
        raise ValueError(f"Only {limit} variable(s) can be provided.")

    return parsed_variables
