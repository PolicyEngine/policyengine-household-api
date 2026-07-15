"""Endpoint-integration coverage for UK /calculate.

policyengine-uk 2.43 changed its Simulation constructor and every UK
calculation 500'd for months without any test noticing; this module
keeps a UK household flowing through the local Flask endpoint (with
auth enabled) in ordinary PR CI.
"""

import json

import pytest

from policyengine_household_api.utils import get_config_value
from tests.data.uk_households import uk_household_single_adult_no_income

# A single unemployed adult aged 25+ with no housing costs receives only
# the Universal Credit standard allowance, so the expected value is the
# 12-month sum of gov.dwp.universal_credit.standard_allowance.amount
# .SINGLE_OLD, including the Universal Credit Act 2025 uplift the model
# applies from April 2026. Recompute when a policyengine-uk bump changes
# UC uprating.
EXPECTED_UNIVERSAL_CREDIT_2026 = 5_079.13


class TestUKCalculate:
    def test_universal_credit_standard_allowance_only(self, client):
        response = client.post(
            "/uk/calculate",
            headers={
                "Content-Type": "application/json",
                "Authorization": (
                    f"Bearer {get_config_value('auth.auth0.test_token')}"
                ),
            },
            json={"household": uk_household_single_adult_no_income},
        )

        assert response.status_code == 200

        result = json.loads(response.data)
        assert result["status"] == "ok"
        assert result["message"] is None

        household = result["result"]
        universal_credit = household["benunits"]["benunit"][
            "universal_credit"
        ]["2026"]
        assert universal_credit == pytest.approx(
            EXPECTED_UNIVERSAL_CREDIT_2026, abs=0.01
        )

        # Inputs must be echoed back unchanged.
        assert household["people"]["adult"]["age"]["2026"] == 30
        assert household["people"]["adult"]["employment_income"]["2026"] == 0
