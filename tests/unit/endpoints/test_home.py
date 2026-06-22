import json

from policyengine_household_api.api import get_api_version
from policyengine_household_api.constants import COUNTRIES


class TestHomeEndpoint:
    def test_returns_json_service_metadata(self, client):
        response = client.get("/")

        assert response.status_code == 200
        assert response.mimetype == "application/json"

        payload = json.loads(response.data)

        assert payload["status"] == "ok"
        assert payload["message"] == "PolicyEngine household API"

        result = payload["result"]
        assert result["docs_url"] == "https://www.policyengine.org/us/api"
        assert (
            result["container_image"]
            == "ghcr.io/policyengine/policyengine-household-api"
        )
        assert (
            result["openapi_spec_url"]
            == "https://household.api.policyengine.org/specification"
        )
        assert result["hosted_calculate_url_template"] == (
            "https://household.api.policyengine.org/{country_id}/calculate"
        )
        assert result["local_calculate_url_template"] == (
            "http://localhost:8080/{country_id}/calculate"
        )
        assert result["health_checks"] == {
            "liveness": "/liveness_check",
            "readiness": "/readiness_check",
        }

    def test_specification_returns_openapi_json(self, client):
        response = client.get("/specification")

        assert response.status_code == 200
        assert response.mimetype == "application/json"

        payload = json.loads(response.data)
        assert payload["openapi"] == "3.0.0"
        assert payload["info"]["title"] == "PolicyEngine Household API"
        assert payload["info"]["version"] == get_api_version()
        calculate = payload["paths"]["/{country_id}/calculate"]["post"]
        assert (
            calculate["requestBody"]["content"]["application/json"]["schema"][
                "$ref"
            ]
            == "#/components/schemas/CalculateRequest"
        )

        country_parameter = next(
            parameter
            for parameter in calculate["parameters"]
            if parameter["name"] == "country_id"
        )
        assert country_parameter["schema"]["enum"] == list(COUNTRIES)

        calculate_request = payload["components"]["schemas"]["CalculateRequest"]
        assert calculate_request["properties"]["version"]["default"] == "current"
        assert "403" not in calculate["responses"]

        assert "bearerAuth" in payload["components"]["securitySchemes"]
        assert "/analytics/calculate/requests" not in payload["paths"]
        assert not any(
            schema_name.startswith("CalculateAnalytics")
            for schema_name in payload["components"]["schemas"]
        )
