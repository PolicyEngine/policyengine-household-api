import pytest
from policyengine_household_api.api import app

pytest_plugins = [
    "tests.fixtures.data.analytics_setup",
    "tests.fixtures.data.analytics_setup_patches",
    "tests.fixtures.decorators.auth",
    "tests.fixtures.decorators.analytics",
    "tests.fixtures.decorators.analytics_patches",
    "tests.fixtures.endpoints.analytics",
    "tests.fixtures.endpoints.household",
    "tests.fixtures.utils.config_loader",
]


@pytest.fixture(autouse=True)
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client
