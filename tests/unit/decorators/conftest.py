from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def disable_variable_usage_extraction():
    with patch(
        "policyengine_household_api.decorators.analytics._collect_variable_usage",
        return_value=False,
    ):
        yield
