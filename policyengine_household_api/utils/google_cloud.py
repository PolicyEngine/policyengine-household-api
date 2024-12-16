from google.cloud import storage


def upload_json_to_cloud_storage(bucket_name: str, input_json: str, destination_blob_name):
    """
    Uploads a JSON-formatted string to a Cloud Storage bucket. Modified from Google Cloud documentation:
    https://cloud.google.com/storage/docs/uploading-objects#uploading-an-object
    """
    # The ID of your GCS bucket
    # bucket_name = "your-bucket-name"
    # The path to your file to upload
    # source_file_name = "local/path/to/file"
    # The ID of your GCS object
    # destination_blob_name = "storage-object-name"

    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)

    blob.upload_from_string(
        data=input_json,
        content_type="application/json",
    )

    print(
        f"JSON uploaded to {destination_blob_name}."
    )

