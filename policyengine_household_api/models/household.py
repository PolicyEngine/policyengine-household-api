from pydantic import BaseModel, RootModel
from typing import Union, Optional, Any
from enum import Enum


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


class HouseholdVariable(RootModel):
    root: Union[dict[str, Any], list[str]]


class HouseholdEntity(RootModel):
    root: dict[str, HouseholdVariable]


class HouseholdModelGeneric(BaseModel):
    households: dict[str, HouseholdEntity]
    people: dict[str, HouseholdEntity]


class HouseholdModelUS(HouseholdModelGeneric):
    families: dict[str, HouseholdEntity]
    spm_units: dict[str, HouseholdEntity]
    tax_units: dict[str, HouseholdEntity]
    marital_units: dict[str, HouseholdEntity]


class HouseholdModelUK(HouseholdModelGeneric):
    benunits: dict[str, HouseholdEntity]


# Typing alias for all three possible household models
HouseholdModel = Union[
    HouseholdModelUS, HouseholdModelUK, HouseholdModelGeneric
]
