import json
from pathlib import Path


CALCULATE_US_1_DATA_PATH = (
    Path(__file__).parents[1]
    / "to_refactor"
    / "python"
    / "data"
    / "calculate_us_1_data.json"
)


def test_malformed_token(deployed_api):
    response = deployed_api.post(
        "/us/calculate",
        headers={
            "Authorization": "Bearer garbage_token",
        },
        json_body=json.loads(CALCULATE_US_1_DATA_PATH.read_text()),
    )

    assert response.status_code == 401


def test_no_token(deployed_api):
    response = deployed_api.post(
        "/us/calculate",
        json_body={"household": {}},
    )

    assert response.status_code == 401
