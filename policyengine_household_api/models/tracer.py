import json
import re
from uuid import UUID, uuid4

from policyengine_household_api.constants import COUNTRY_PACKAGE_VERSIONS
from policyengine_household_api.utils.google_cloud import (
    upload_json_to_cloud_storage,
    download_json_from_cloud_storage,
)

TEST_UUID = "123e4567-e89b-12d3-a456-426614174000"
TEST_TRACER = [
    "only_government_benefit <1500>",
    "    market_income <1000>",
    "        employment_income <1000>",
    "            main_employment_income <1000 >",
    "    non_market_income <500>",
    "        pension_income <500>",
]


class Tracer:
    """
    A class to represent a tracer output for household policy calculations.
    Can be initialized using either a UUID (for fetching from Cloud Storage)
    or a list of log lines (for parsing, followed by uploading to Cloud Storage).

    Args:
        country_id (str): The country ID for which the tracer output is generated.
        tracer_uuid (str, optional): The UUID of a tracer already stored in
            Cloud Storage. If provided, the tracer will be fetched from the bucket.
            Defaults to None.
        tracer (list[str], optional): The log lines to construct the tracer data.
            If provided, the tracer will be constructed from these log lines, then
            uploaded to Cloud Storage. Defaults to None.
    """

    cloud_bucket_name = "policyengine-test-bucket"

    def __init__(
        self,
        country_id: str,
        tracer_uuid: str | None = None,
        tracer: list[str] | None = None,
    ):
        # Mandate country ID - raise if not provided
        if country_id is None:
            raise ValueError("Country ID must be provided.")

        self.country_id = country_id
        # If a UUID exists, assume we're fetching from bucket
        if tracer_uuid is not None:
            self.tracer_uuid: str = tracer_uuid
            self.storage_object: dict = self.download_from_cloud_storage(
                tracer_uuid
            )

        # Otherwise, assume we're passing log lines to Cloud Storage
        elif tracer is not None:
            self.storage_object: dict = self._construct_storage_object(
                tracer, country_id
            )
            self.tracer_uuid: str = self.storage_object["uuid"]
        else:
            raise ValueError(
                "Either tracer_UUID or tracer value must be provided."
            )

        self.package_version: str = self.storage_object["package_version"]
        self.tracer: list[str] = self.storage_object["tracer"]

    def parse_tracer_output(self, target_variable: str) -> list[str]:
        """
        Given a household tracer output, parse its contents to find
        the calculation tree for a specific variable.

        Args:
            target_variable (str): The variable to find in the tracer output.

        Returns:
            list[str]: The calculation tree excerpt for the target variable.
        """
        result: list[str] = []
        target_indent: int | None = None
        capturing: bool = False

        # Create a regex pattern to match the exact variable name
        # This will match the variable name followed by optional whitespace,
        # then optional angle brackets with any content, then optional whitespace
        pattern: re.Pattern[str] = (
            rf"^(\s*)({re.escape(target_variable)})\s*(?:<[^>]*>)?\s*"
        )

        for line in self.tracer:
            # Count leading spaces to determine indentation level
            indent = len(line) - len(line.strip())

            # Check if this line matches our target variable
            match: bool = re.match(pattern, line)
            if match and not capturing:
                target_indent = indent
                capturing = True
                result.append(line)
            elif capturing:
                # Stop capturing if we encounter a line with less indentation than the target
                if indent <= target_indent:
                    break
                # Capture dependencies (lines with greater indentation)
                result.append(line)

        return result

    def upload_to_cloud_storage(self):
        """
        Store the tracer output in a Google Cloud bucket.
        """

        # JSON-ify the log lines

        # JSON-ify the storage object
        storage_object_json: str = json.dumps(self.storage_object)

        # Write tracer output to Google Cloud bucket
        try:
            upload_json_to_cloud_storage(
                bucket_name=self.cloud_bucket_name,
                input_json=storage_object_json,
                destination_blob_name=self.tracer_uuid,
            )
        except Exception as e:
            print(
                f"Error uploading tracer storage object to Google Cloud bucket: {e}"
            )

    def download_from_cloud_storage(self, tracer_uuid: str) -> dict:
        """
        Given a UUID, fetch a storage object from a Google Cloud bucket and
        return it as a dictionary.

        Args:
            tracer_uuid (str): The identifier of the item to fetch.

        Returns:
            dict: The fetched item.
        """

        storage_object_json = download_json_from_cloud_storage(
            bucket_name=self.cloud_bucket_name, source_blob_name=tracer_uuid
        )

        return json.loads(storage_object_json)

    def _construct_storage_object(
        self, tracer: list[str], country_id: str
    ) -> dict:
        """
        Construct object that will be stored within Cloud Storage.

        Args:
            tracer (list[str]): The log lines to construct tracer data from.

        Returns:
            dict: The constructed storage object.
        """
        uuid: UUID = uuid4()
        package_version = COUNTRY_PACKAGE_VERSIONS[country_id]

        return {
            "uuid": str(uuid),
            "package_version": package_version,
            "tracer": tracer,
        }
