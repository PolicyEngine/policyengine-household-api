from pydantic import BaseModel, create_model
from typing import Any, Enum, Literal, Union, Optional
from policyengine_us import entities as entities_us
from policyengine_uk import entities as entities_uk


# Dynamically generate entity schema
household_entities_us: dict[str, type] = {
    entity.plural: HouseholdEntity for entity in entities_us
}
household_entities_uk: dict[str, type] = {
    entity.plural: HouseholdEntity for entity in entities_uk
}

example_household_us = {
    "people": {
        "you": {"age": {"2024": 40}, "employment_income": {"2024": 29000}},
        "your first dependent": {
            "age": {"2024": 5},
            "employment_income": {"2024": 0},
            "is_tax_unit_dependent": {"2024": True},
        },
    },
    "families": {"your family": {"members": ["you", "your first dependent"]}},
    "spm_units": {
        "your household": {"members": ["you", "your first dependent"]}
    },
    "tax_units": {
        "your tax unit": {"members": ["you", "your first dependent"]}
    },
    "households": {
        "your household": {
            "members": ["you", "your first dependent"],
            "state_name": {"2024": "CA"},
        }
    },
    "marital_units": {
        "your marital unit": {"members": ["you"]},
        "your first dependent's marital unit": {
            "members": ["your first dependent"],
            "marital_unit_id": {"2024": 1},
        },
    },
}


class HouseholdVariable(BaseModel):
    __root__: dict[str, int | float | str | bool | Enum]


class HouseholdEntity(BaseModel):
    members: Optional[list[str]]
    __root__: Optional[HouseholdVariable]


class HouseholdEntityGroup(BaseModel):
    __root__: dict[str, HouseholdEntity]


class HouseholdModelGeneric(BaseModel):
    households: dict[str, HouseholdEntityGroup]
    people: dict[str, HouseholdEntityGroup]


class HouseholdModelUS(HouseholdModelGeneric):
    families: dict[str, HouseholdEntityGroup]
    spm_units: dict[str, HouseholdEntityGroup]
    tax_units: dict[str, HouseholdEntityGroup]
    marital_units: dict[str, HouseholdEntityGroup]


class HouseholdModelUK(HouseholdModelGeneric):
    benunits: dict[str, HouseholdEntityGroup]


# Typing alias for all three possible household models
HouseholdModel = Union[
    HouseholdModelUS, HouseholdModelUK, HouseholdModelGeneric
]
