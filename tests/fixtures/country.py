valid_household_requesting_ctc_calculation = {
    "people": {
        "you": {
            "age": {"2024": 40},
        }
    },
    "tax_units": {"tax_unit": {"members": ["you"], "ctc": {"2024": None}}},
    "families": {"family": {"members": ["you"]}},
    "households": {"household": {"members": ["you"]}},
    "spm_units": {"spm_unit": {"members": ["you"]}},
}

country_package_name_us = "policyengine_us"
country_id_us = "us"

us_household_requesting_income_tax = {
    "people": {
        "you": {
            "age": {"2024": 40},
            "employment_income": {"2024": 50_000},
        }
    },
    "tax_units": {
        "tax_unit": {"members": ["you"], "income_tax": {"2024": None}}
    },
    "families": {"family": {"members": ["you"]}},
    "households": {"household": {"members": ["you"]}},
    "spm_units": {"spm_unit": {"members": ["you"]}},
}

us_standard_deduction_reform = {
    "gov.irs.deductions.standard.amount.SINGLE": {
        "2024-01-01.2024-12-31": "30000",
    }
}
