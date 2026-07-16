"""UK household payloads shared by the unit and deployed test lanes.

UK calculations broke silently when policyengine-uk 2.43 changed its
Simulation constructor because no test lane sent a UK household through
/calculate; these payloads exist so both lanes keep that path covered.
"""

uk_household_requesting_universal_credit = {
    "people": {
        "parent": {
            "age": {"2026": 30},
            "employment_income": {"2026": 15_000},
        },
        "child": {
            "age": {"2026": 5},
        },
    },
    "benunits": {
        "benunit": {
            "members": ["parent", "child"],
            "universal_credit": {"2026": None},
        }
    },
    "households": {
        "household": {
            "members": ["parent", "child"],
            "region": {"2026": "LONDON"},
            "tenure_type": {"2026": "RENT_PRIVATELY"},
            "rent": {"2026": 15_600},
        }
    },
}

# Minimal case whose expected value is derivable by hand: a single
# unemployed adult aged 25+ with no housing costs receives only the
# Universal Credit standard allowance — no elements, no taper.
uk_household_single_adult_no_income = {
    "people": {
        "adult": {
            "age": {"2026": 30},
            "employment_income": {"2026": 0},
        }
    },
    "benunits": {
        "benunit": {
            "members": ["adult"],
            "universal_credit": {"2026": None},
        }
    },
    "households": {"household": {"members": ["adult"]}},
}

uk_household_requesting_enum_outputs = {
    "people": {"parent": {"age": {"2026": 30}}},
    "benunits": {"benunit": {"members": ["parent"]}},
    "households": {
        "household": {
            "members": ["parent"],
            "region": {"2026": "LONDON"},
            "country": {"2026": None},
        }
    },
}

uk_household_requesting_income_tax = {
    "people": {
        "parent": {
            "age": {"2026": 30},
            "employment_income": {"2026": 15_000},
            "income_tax": {"2026": None},
        }
    },
    "benunits": {"benunit": {"members": ["parent"]}},
    "households": {"household": {"members": ["parent"]}},
}

# The value is a string on purpose: the API casts reform values to the
# parameter's node type, and that contract must hold on the wrapper
# simulation path too.
uk_personal_allowance_reform = {
    "gov.hmrc.income_tax.allowances.personal_allowance.amount": {
        "2026-01-01.2026-12-31": "15000",
    }
}

# A high earner fails the marriage allowance income condition under
# current law; only the structural reform gated by the parameter below
# removes that condition. Distinguishes "parameter changed" from
# "structural reform actually applied".
uk_household_married_requesting_marriage_allowance = {
    "people": {
        "earner": {
            "age": {"2026": 40},
            "employment_income": {"2026": 80_000},
            "marriage_allowance": {"2026": None},
        },
        "partner": {
            "age": {"2026": 40},
            "employment_income": {"2026": 0},
        },
    },
    "benunits": {
        "benunit": {
            "members": ["earner", "partner"],
            "is_married": {"2026": True},
        }
    },
    "households": {"household": {"members": ["earner", "partner"]}},
}

# The period must cover the wrapper's default input period (2025 as of
# policyengine-uk 2.88): structural-trigger parameters are sampled at
# that instant during Simulation construction, not at the calculation
# period.
uk_marriage_allowance_structural_reform = {
    "gov.contrib.cps.marriage_tax_reforms.expanded_ma.remove_income_condition": {
        "2025-01-01.2030-12-31": True,
    }
}

uk_household_with_axes = {
    "people": {"parent": {"age": {"2026": 30}}},
    "benunits": {
        "benunit": {
            "members": ["parent"],
            "universal_credit": {"2026": None},
        }
    },
    # `country` pins enum outputs under axes: the wrapper Simulation
    # returns them as decoded string arrays.
    "households": {
        "household": {"members": ["parent"], "country": {"2026": None}}
    },
    "axes": [
        [
            {
                "name": "employment_income",
                "count": 3,
                "min": 0,
                "max": 30_000,
                "period": "2026",
            }
        ]
    ],
}
