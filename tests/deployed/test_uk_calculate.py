"""Deployed smoke coverage for UK /calculate.

policyengine-uk 2.43 changed its Simulation constructor and every UK
calculation 500'd for months without any deployed test noticing; this
module keeps a UK household flowing through each deployed route.
"""

from tests.data.uk_households import (
    uk_household_requesting_universal_credit,
)


class TestUKCalculate:
    def test_universal_credit_calculation(
        self,
        deployed_api,
        auth_token,
        uk_request_version,
        expected_backend,
    ):
        request_body = {
            "household": uk_household_requesting_universal_credit,
        }
        if uk_request_version:
            request_body["version"] = uk_request_version

        response = deployed_api.post(
            "/uk/calculate",
            headers={
                "Authorization": f"Bearer {auth_token}",
            },
            json_body=request_body,
        )

        assert response.status_code == 200
        if expected_backend:
            assert (
                response.headers["X-PolicyEngine-Backend"] == expected_backend
            )

        result = response.json()
        assert result["status"] == "ok"
        assert result["message"] is None

        household = result["result"]
        universal_credit = household["benunits"]["benunit"][
            "universal_credit"
        ]["2026"]
        assert isinstance(universal_credit, (int, float))
        assert universal_credit > 0

        # Inputs must be echoed back unchanged.
        assert (
            household["people"]["parent"]["employment_income"]["2026"]
            == 15_000
        )
