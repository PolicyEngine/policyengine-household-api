import pytest
from policyengine_household_api.api import app


@pytest.fixture
def client(autouse=True):
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client
