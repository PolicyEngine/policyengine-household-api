import json


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
        assert (
            payload["paths"]["/{country_id}/calculate"]["post"]["requestBody"][
                "content"
            ]["application/json"]["schema"]["$ref"]
            == "#/components/schemas/CalculateRequest"
        )
        assert "bearerAuth" in payload["components"]["securitySchemes"]
