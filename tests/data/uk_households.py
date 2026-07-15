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

uk_household_with_axes = {
    "people": {"parent": {"age": {"2026": 30}}},
    "benunits": {
        "benunit": {
            "members": ["parent"],
            "universal_credit": {"2026": None},
        }
    },
    "households": {"household": {"members": ["parent"]}},
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
