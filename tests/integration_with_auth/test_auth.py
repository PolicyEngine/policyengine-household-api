import os
from tests.to_refactor.fixtures import client

# Note that this does not test the passage of a functioning token;
# that is already handled by test_liveness in another file
def test_malformed_token(client):
    """Test that a malformed token, when passed to the API, returns a 401"""
    response = client.post(
        "/us/calculate",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer garbage_token",
        },
        data=open(
            "./tests/to_refactor/python/data/calculate_us_1_data.json",
            "r",
            encoding="utf-8",
        ),
    )
    assert response.status_code == 401


def test_no_token(client):
    """Test that API returns 401 when no token is passed"""
    response = client.post(
        "/us/calculate",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 401
