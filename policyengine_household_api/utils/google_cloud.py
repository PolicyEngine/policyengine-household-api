from google.cloud import storage
import json
from typing import Annotated


def upload_json_to_cloud_storage(
    bucket_name: str, input_json: str, destination_blob_name
):
    """
    Uploads a JSON-formatted string to a Cloud Storage bucket. Modified from Google Cloud documentation:
    https://cloud.google.com/storage/docs/uploading-objects#uploading-an-object
    """

    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)

    blob.upload_from_string(
        data=input_json,
        content_type="application/json",
    )

    print(f"JSON uploaded to {destination_blob_name}.")


def download_json_from_cloud_storage(
    bucket_name: str, source_blob_name: str
) -> Annotated[str, "JSON-formatted string"]:
    """
    Downloads a JSON-formatted string from a Cloud Storage bucket. Modified from Google Cloud documentation:
    https://cloud.google.com/storage/docs/downloading-objects-into-memory#downloading-an-object-into-memory
    """
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(source_blob_name)

    return blob.download_as_text()
