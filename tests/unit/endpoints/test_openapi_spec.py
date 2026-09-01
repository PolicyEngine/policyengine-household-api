import json
import re

import pytest
import yaml
from openapi_spec_validator import validate

from policyengine_household_api import api
from policyengine_household_api.constants import COUNTRIES


HTTP_METHODS = {"delete", "get", "patch", "post", "put"}
INTENTIONALLY_UNDOCUMENTED_OPERATIONS = {
    ("/{country_id}/calculate_demo", "post"),
}


def _runtime_operations():
    operations = set()
    for rule in api.app.url_map.iter_rules():
        if rule.endpoint == "static":
            continue
        path = re.sub(
            r"<(?:(?:[^:>]+):)?([^>]+)>",
            r"{\1}",
            rule.rule,
        )
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            operations.add((path, method.lower()))
    return operations


def _documented_operations(spec):
    return {
        (path, method)
        for path, path_item in spec["paths"].items()
        for method in path_item
        if method in HTTP_METHODS
    }


def test_openapi_loader_rejects_duplicate_mapping_keys(monkeypatch, tmp_path):
    spec_path = tmp_path / "openapi.yaml"
    spec_path.write_text(
        """
openapi: 3.0.0
info:
  title: First title
  title: Second title
  version: 1.0.0
paths: {}
""".lstrip()
    )
    monkeypatch.setattr(api, "OPENAPI_SPEC_PATH", spec_path)

    with pytest.raises(yaml.constructor.ConstructorError, match="title"):
        api.load_openapi_spec()


def test_openapi_document_is_valid():
    validate(api.load_openapi_spec())


def test_openapi_operations_match_runtime_except_calculate_demo():
    spec = api.load_openapi_spec()
    runtime_operations = _runtime_operations()

    assert INTENTIONALLY_UNDOCUMENTED_OPERATIONS <= runtime_operations
    assert _documented_operations(spec) == (
        runtime_operations - INTENTIONALLY_UNDOCUMENTED_OPERATIONS
    )
    assert "/{country_id}/calculate_demo" not in spec["paths"]


def test_calculate_documents_all_supported_countries():
    spec = api.load_openapi_spec()
    country_parameter = next(
        parameter
        for parameter in spec["paths"]["/{country_id}/calculate"]["post"][
            "parameters"
        ]
        if parameter["name"] == "country_id"
    )

    assert set(country_parameter["schema"]["enum"]) == set(COUNTRIES)


def test_home_response_matches_openapi_schema(client):
    response_payload = json.loads(client.get("/").data)
    documented_result = api.load_openapi_spec()["paths"]["/"]["get"][
        "responses"
    ]["200"]["content"]["application/json"]["schema"]["properties"]["result"][
        "properties"
    ]

    assert set(documented_result) == set(response_payload["result"])
    assert set(documented_result["health_checks"]["properties"]) == set(
        response_payload["result"]["health_checks"]
    )
