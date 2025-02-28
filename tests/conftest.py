import pytest
from policyengine_household_api.api import app


@pytest.fixture(autouse=True)
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client
