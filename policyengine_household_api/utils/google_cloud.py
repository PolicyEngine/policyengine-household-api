import json
from uuid import UUID, uuid4

from policyengine_household_api.constants import COUNTRY_PACKAGE_VERSIONS

TEST_UUID = "123e4567-e89b-12d3-a456-426614174000"

def store_in_cloud_bucket(log_lines: list, country_id: str) -> UUID:
  """
  Store something in a Google Cloud bucket and return its item identifier. 
  This function remains under construction and is subject to significant change.

  Args:
      log_lines (list): A list of log lines to store in the cloud bucket.

  Returns:
      str: The identifier of the stored item.
  """

  # JSON-ify the log lines
  log_json: str = json.dumps(log_lines)

  # Generate a UUID for the complete tracer run
  tracer_uuid: UUID = uuid4()

  # Find country package version to save
  package_version: str = COUNTRY_PACKAGE_VERSIONS[country_id]

  # Write tracer output to Google Cloud bucket - not yet implemented
  print("Writing tracer output to Google Cloud bucket not yet implemented")

  # Return UUID
  return tracer_uuid

def fetch_from_cloud_bucket(tracer_uuid: str) -> dict:
  """
  Fetch something from a Google Cloud bucket and return it as a dictionary. 
  This function remains under construction and is subject to significant change.

  Args:
      tracer_uuid (str): The identifier of the item to fetch.

  Returns:
      dict: The fetched item.
  """

  # Fetch the tracer output from the Google Cloud bucket - not yet implemented
  print("Fetching tracer output from Google Cloud bucket not yet implemented")

  # Return dummy data
  return {
    "uuid": TEST_UUID,
    "variable": "income",
    "package_version": "0.1.0",
    "tracer": [
        "only_government_benefit <1500>",
        "    market_income <1000>",
        "        employment_income <1000>",
        "            main_employment_income <1000 >",
        "    non_market_income <500>",
        "        pension_income <500>",
    ]
  }