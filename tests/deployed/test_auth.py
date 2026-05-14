import json
from pathlib import Path


CALCULATE_US_1_DATA_PATH = (
    Path(__file__).parents[1]
    / "to_refactor"
    / "python"
    / "data"
    / "calculate_us_1_data.json"
)


def _calculate_body(request_version=None):
    body = json.loads(CALCULATE_US_1_DATA_PATH.read_text())
    if request_version:
        body["version"] = request_version
    return body


def test_malformed_token(deployed_api, request_version):
    response = deployed_api.post(
        "/us/calculate",
        headers={
            "Authorization": "Bearer garbage_token",
        },
        json_body=_calculate_body(request_version),
    )

    assert response.status_code == 401


def test_no_token(deployed_api, request_version):
    body = {"household": {}}
    if request_version:
        body["version"] = request_version

    response = deployed_api.post(
        "/us/calculate",
        json_body=body,
    )

    assert response.status_code == 401
