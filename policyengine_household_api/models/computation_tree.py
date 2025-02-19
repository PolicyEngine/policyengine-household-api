import json
import re
import sys
from uuid import UUID, uuid4
from pydantic import RootModel
from typing import Annotated
from policyengine_household_api.models import CountryId

from policyengine_household_api.constants import COUNTRY_PACKAGE_VERSIONS
from policyengine_household_api.utils.google_cloud import (
    upload_json_to_cloud_storage,
    download_json_from_cloud_storage,
)

# To be removed - will be included in tests when written
TEST_UUID = "123e4567-e89b-12d3-a456-426614174000"
TEST_computation_tree = [
    "only_government_benefit <1500>",
    "    market_income <1000>",
    "        employment_income <1000>",
    "            main_employment_income <1000 >",
    "    non_market_income <500>",
    "        pension_income <500>",
]


class EntityDescription(RootModel):
    root: dict[
        Annotated[str, "An entity group, e.g., people"],
        list[Annotated[str, "An entity, e.g., 'your partner'"]],
    ]


class ComputationTree:
    """
    A class to represent a computation tree (previously "tracer") output for
    household policy calculations. Can be initialized using either a UUID
    (for fetching from Cloud Storage) or a list of log lines (for parsing,
    followed by uploading to Cloud Storage).

    Args:
        country_id (str): The country ID for which the computation_tree output is generated.
        computation_tree_uuid (str, optional): The UUID of a computation_tree already stored in
            Cloud Storage. If provided, the computation_tree will be fetched from the bucket.
            Defaults to None.
        computation_tree (list[str], optional): The log lines to construct the computation_tree data.
            If provided, the computation_tree will be constructed from these log lines, then
            uploaded to Cloud Storage. Defaults to None.
    """

    cloud_bucket_name = "policyengine-test-bucket"

    def store_computation_tree(
        self,
        country_id: CountryId,
        tree: list[str] | None = None,
        entity_description: EntityDescription | None = None,
    ) -> str:
        try:
            storage_object: dict = self._construct_storage_object(
                country_id=country_id,
                tree=tree,
                entity_description=entity_description,
            )
            uuid: str = storage_object["uuid"]

            tree: list[str] = storage_object["computation_tree"]
            self.tree = tree

            self._upload_to_cloud_storage(
                storage_object=storage_object,
                uuid=uuid,
            )

            return uuid
        except Exception as e:
            print(f"Error storing computation tree: {e}")

    def get_computation_tree(
        self, uuid: str
    ) -> tuple[list[str], EntityDescription]:
        try:
            downloaded_object: dict = self._download_from_cloud_storage(uuid)
            self.tree = downloaded_object["computation_tree"]
            self.entity_description = EntityDescription.model_validate(
                downloaded_object["entity_description"]
            )
            return self.tree, self.entity_description
        except Exception as e:
            print(f"Error getting computation tree: {e}")

    def parse_computation_tree_for_variable(self, variable: str) -> list[str]:
        """
        Given a household computation_tree output, parse its contents to find
        the calculation tree for a specific variable.

        Args:
            variable (str): The variable to find in the computation_tree output.

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
            rf"^(\s*)({re.escape(variable)})\s*(?:<[^>]*>)?\s*"
        )

        for line in self.tree:
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

    def _upload_to_cloud_storage(self, storage_object: dict, uuid: str):
        """
        Store the computation_tree output in a Google Cloud bucket.
        """

        # JSON-ify the storage object
        storage_object_json: str = json.dumps(storage_object)

        print(
            f"Uploading computation_tree storage object to Google Cloud bucket...",
            file=sys.stderr,
        )

        # Write computation_tree output to Google Cloud bucket
        try:
            upload_json_to_cloud_storage(
                bucket_name=self.cloud_bucket_name,
                input_json=storage_object_json,
                destination_blob_name=uuid,
            )
        except Exception as e:
            print(
                f"Error uploading computation_tree storage object to Google Cloud bucket: {e}"
            )

    def _download_from_cloud_storage(self, uuid: str) -> dict:
        """
        Given a UUID, fetch a storage object from a Google Cloud bucket and
        return it as a dictionary.

        Returns:
            dict: The fetched item.
        """

        storage_object_json = download_json_from_cloud_storage(
            bucket_name=self.cloud_bucket_name,
            source_blob_name=uuid,
        )

        return json.loads(storage_object_json)

    def _construct_storage_object(
        self,
        country_id: CountryId,
        tree: list[str],
        entity_description: EntityDescription,
    ) -> dict:
        """
        Construct object that will be stored within Cloud Storage.

        Args:
            computation_tree (list[str]): The log lines to construct computation_tree data from.

        Returns:
            dict: The constructed storage object.
        """
        uuid: UUID = uuid4()
        package_version = COUNTRY_PACKAGE_VERSIONS[country_id]

        return {
            "uuid": str(uuid),
            "package_version": package_version,
            "computation_tree": tree,
            "entity_description": entity_description.dict(),
        }
