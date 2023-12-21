import pytest
import json
import requests
from policyengine_api_light.api import app

@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client

def extract_json_from_file(filepath):
  extracted_data = None
  
  with open(
    filepath,
    "r",
    encoding="utf-8"
  ) as file:
    extracted_data = json.load(file)
  
  return extracted_data