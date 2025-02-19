from google.cloud import storage
from werkzeug.exceptions import HTTPException
from pydantic import BaseModel
import json
from typing import Annotated, Any, Literal
from uuid import UUID


class GoogleCloudStorageManager:
    """
    A class to manage uploading and downloading data to/from Google Cloud Buckets
    """

    DEFAULT_BUCKET_NAME: str = "policyengine-test-bucket"

    def store(
        self,
        uuid: UUID,
        data: BaseModel,
        target_bucket: str = DEFAULT_BUCKET_NAME,
    ):
        # Confirm that data is a Pydantic model
        if not isinstance(data, BaseModel):
            raise TypeError("Data must be a Pydantic model.")

        # Deserialize inbound data to JSON
        json_data = self._deserialize_pydantic_to_json(data)

        # Upload data to Google Cloud Storage
        self._upload_json_to_cloud_storage(
            bucket_name=target_bucket,
            input_json=json_data,
            destination_blob_name=str(uuid),
        )

    def get(
        self,
        uuid: UUID,
        deserializer: type[BaseModel],
        source_bucket: str = DEFAULT_BUCKET_NAME,
    ) -> BaseModel:
        if not issubclass(deserializer, BaseModel):
            raise TypeError("Deserialization model must be a Pydantic model.")

        # Download data from Google Cloud Storage
        # Return in default format; relevant model will serialize
        json_data: str = self._download_json_from_cloud_storage(
            bucket_name=source_bucket, source_blob_name=str(uuid)
        )
        return self._serialize_json_to_pydantic(json_data, deserializer)

    def _deserialize_pydantic_to_json(
        self, data: BaseModel
    ) -> Annotated[str, "JSON-formatted string"]:
        """
        Converts a Pydantic model to a JSON-formatted
        string.
        """

        try:
            return data.model_dump_json()
        except Exception as e:
            raise HTTPException(
                description=f"Error deserializing Pydantic model to JSON: {e}",
            )

    def _serialize_json_to_pydantic(
        self,
        data: Annotated[str, "JSON-formatted string"],
        deserializer: type[BaseModel],
    ) -> BaseModel:
        """
        Converts a JSON-formatted string to a Pydantic model.
        """

        try:
            data_dict: dict[str, Any] = json.loads(data)

            return deserializer.model_validate(data_dict)
        except Exception as e:
            raise HTTPException(
                description=f"Error serializing JSON to Pydantic model: {e}",
            )

    def _upload_json_to_cloud_storage(
        self, bucket_name: str, input_json: str, destination_blob_name
    ):
        """
        Uploads a JSON-formatted string to a Cloud Storage bucket. Modified from Google Cloud documentation:
        https://cloud.google.com/storage/docs/uploading-objects#uploading-an-object
        """

        try:
            storage_client = storage.Client()
            bucket = storage_client.bucket(bucket_name)
            blob = bucket.blob(destination_blob_name)

            blob.upload_from_string(
                data=input_json,
                content_type="application/json",
            )

            print(f"JSON uploaded to {destination_blob_name}.")
        except Exception as e:
            raise HTTPException(
                description=f"Error uploading JSON to {destination_blob_name}: {e}",
            )

    def _download_json_from_cloud_storage(
        self, bucket_name: str, source_blob_name: str
    ) -> Annotated[str, "JSON-formatted string"]:
        """
        Downloads a JSON-formatted string from a Cloud Storage bucket. Modified from Google Cloud documentation:
        https://cloud.google.com/storage/docs/downloading-objects-into-memory#downloading-an-object-into-memory
        """
        try:
            storage_client = storage.Client()
            bucket = storage_client.bucket(bucket_name)
            blob = bucket.blob(source_blob_name)

            return blob.download_as_text()
        except Exception as e:
            raise HTTPException(
                description=f"Error downloading JSON from {source_blob_name}: {e}",
            )
