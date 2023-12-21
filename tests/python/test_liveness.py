from tests.python.utils import client


def test_calculate_liveness(client):
    """This tests that, when passed relevant data, calculate endpoint functions properly"""
    response = client.post(
        "/us/calculate",
        headers={"Content-Type": "application/json"},
        data=open(
            "./tests/python/data/calculate_us_1_data.json",
            "r",
            encoding="utf-8",
        ),
    )
    assert response.status_code == 200, response.text


def test_calculate_full_liveness(client):
    """This tests that, when passed relevant data, calculate endpoint functions properly"""
    response = client.post(
        "/us/calculate-full",
        headers={"Content-Type": "application/json"},
        data=open(
            "./tests/python/data/calculate_us_1_data.json",
            "r",
            encoding="utf-8",
        ),
    )
    assert response.status_code == 200, response.text
