benefits_navigator_household = {
    "households": {
        "household": {
            "zip_code": {"2025": "90101"},
            "lives_in_vehicle": {"2025": False},
            "members": ["you"],
            "ca_care": {"2025": None},
            "ca_care_eligible": {"2025": None},
            "ca_fera": {"2025": None},
            "ca_fera_eligible": {"2025": None},
            "ca_tanf_region1": {"2025": True},
            "state_code_str": {"2025": "CA"},
            "ca_la_ez_save": {"2025-3": None},
            "ca_la_ez_save_eligible": {"2025-3": None},
            "in_la": {"2025": True},
        }
    },
    "people": {
        "you": {
            "age": {"2025": 19},
            "was_in_foster_care": {"2025": True},
            "immigration_status_str": {"2025": "CITIZEN"},
            "employment_income": {"2025": 1111},
            "medical_out_of_pocket_expenses": {"2025": 132},
            "rent": {"2025": 1332},
            "is_aca_eshi_eligible": {"2025": False},
            "is_pregnant": {"2025": True},
            "ca_calworks_child_care_time_category": {"2025": "MONTHLY"},
            "ca_la_expectant_parent_payment_eligible": {"2025-3": None},
            "ca_la_expectant_parent_payment": {"2025-3": None},
            "ca_foster_care_minor_dependent": {"2025-3": None},
            "current_pregnancy_month": {"2025-3": 9},
            "is_in_foster_care": {"2025-3": True},
            "medicaid": {"2025": None},
            "is_medicaid_eligible": {"2025": None},
            "wic": {"2025": None},
            # "is_aca_ptc_eligible": {"2025": None},
            "is_ssi_aged": {"2025": None},
        }
    },
    "tax_units": {
        "tax_unit": {
            "tax_unit_is_joint": {"2025": False},
            "members": ["you"],
            # There may be a bug in aca_ptc/premium_tax_credit;
            # this currently just returns None in testing;
            # un-comment when we can confirm that's running smoothly
            # "premium_tax_credit": { "2025": None },
            "eitc": {"2025": None},
            "eitc_eligible": {"2025": None},
            "ca_eitc": {"2025": None},
            "ca_eitc_eligible": {"2025": None},
            "ctc": {"2025": None},
            "refundable_ctc": {"2025": None},
            "ca_yctc": {"2025": None},
            # "aca_ptc_ca": {"2025": None},
            "ca_renter_credit": {"2025": None},
            "cdcc": {"2025": None},
            "ca_cdcc": {"2025": None},
            "ca_foster_youth_tax_credit": {"2025": None},
            "income_tax_before_credits": {"2025": None},
            "income_tax_before_refundable_credits": {"2025": None},
            "income_tax_refundable_credits": {"2025": None},
            "income_tax_capped_non_refundable_credits": {"2025": None},
            "income_tax_non_refundable_credits": {"2025": None},
            "income_tax": {"2025": None},
            "ca_income_tax_before_credits": {"2025": None},
            "ca_income_tax_before_refundable_credits": {"2025": None},
        }
    },
    "families": {"family": {"members": ["you"]}},
    "spm_units": {
        "spm_unit": {
            "members": ["you"],
            "ca_tanf": {"2025": None},
            "ca_tanf_eligible": {"2025": None},
            "snap": {"2025": None},
            "is_snap_eligible": {"2025": None},
            "lifeline": {"2025": None},
            "is_lifeline_eligible": {"2025": None},
            "phone_cost": {"2025": 999},
            "la_general_relief": {"2025": None},
            "la_general_relief_eligible": {"2025": None},
            "ca_calworks_child_care": {"2025": None},
            "ca_calworks_child_care_eligible": {"2025": None},
        }
    },
}
