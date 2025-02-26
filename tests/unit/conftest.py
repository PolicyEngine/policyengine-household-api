import pytest
from policyengine_household_api.api import app
from unittest.mock import patch


@pytest.fixture
def client(autouse=True):
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture(autouse=True)
def mock_cloud_upload():
    with patch(
        "policyengine_household_api.utils.google_cloud.GoogleCloudStorageManager._upload_json_to_cloud_storage"
    ) as mock_upload:
        yield mock_upload
