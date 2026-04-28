"""Unit tests for utils/google_cloud.py (GCPError, raise paths)."""

from unittest.mock import patch, MagicMock

import pytest
from pydantic import BaseModel

from policyengine_household_api.utils.google_cloud import (
    GCPError,
    GoogleCloudStorageManager,
)


class _Model(BaseModel):
    value: int


class TestGCPError:
    def test__given_description_kwarg__exception_preserves_description(self):
        err = GCPError(description="boom")
        assert err.description == "boom"
        assert str(err) == "boom"

    def test__given_positional_message__exception_preserves_message(self):
        err = GCPError("boom")
        assert err.description == "boom"
        assert str(err) == "boom"


class TestStorageManagerRaisesGCPError:
    def test__given_download_fails__raises_gcp_error(self):
        manager = GoogleCloudStorageManager()

        with patch(
            "policyengine_household_api.utils.google_cloud.storage.Client",
            side_effect=RuntimeError("denied"),
        ):
            with pytest.raises(GCPError) as info:
                manager._download_json_from_cloud_storage(
                    bucket_name="b", source_blob_name="x"
                )
        assert "denied" in info.value.description

    def test__given_pydantic_serialize_fails__raises_gcp_error(self):
        manager = GoogleCloudStorageManager()

        bad = MagicMock(spec=BaseModel)
        bad.model_dump_json.side_effect = RuntimeError("boom")

        with pytest.raises(GCPError) as info:
            manager._deserialize_pydantic_to_json(bad)
        assert "boom" in info.value.description
