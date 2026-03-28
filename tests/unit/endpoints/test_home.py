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
        assert result["hosted_calculate_url"] == (
            "https://household.api.policyengine.org/us/calculate"
        )
        assert result["local_calculate_url"] == "http://localhost:8080/us/calculate"
        assert result["health_checks"] == {
            "liveness": "/liveness_check",
            "readiness": "/readiness_check",
        }
