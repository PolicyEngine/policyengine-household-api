import json
import re
import sys
from uuid import UUID, uuid4
from pydantic import RootModel, BaseModel
from typing import Annotated

from policyengine_household_api.constants import COUNTRY_PACKAGE_VERSIONS

# To be removed - will be included in tests when written
TEST_UUID = "123e4567-e89b-12d3-a456-426614174000"
TEST_computation_tree = [
    "only_government_benefit <1500>",
    "    market_income <1000>",
    "        employment_income <1000>",
    "            main_employment_income <1000 >",
    "    non_market_income <500>",
    "        pension_income <500>",
]


class EntityDescription(RootModel):
    root: dict[
        Annotated[str, "An entity group, e.g., people"],
        list[Annotated[str, "An entity, e.g., 'your partner'"]],
    ]


class ComputationTree(BaseModel):
    uuid: UUID
    country_id: str
    tree: list[str]
    entity_description: EntityDescription
