from pathlib import Path
from importlib.metadata import version

REPO = Path(__file__).parents[1]
GET = "GET"
POST = "POST"
UPDATE = "UPDATE"
LIST = "LIST"
VERSION = "0.13.3"
COUNTRIES = ("uk", "us", "ca", "ng", "il")
COUNTRY_PACKAGE_NAMES = (
    "policyengine_uk",
    "policyengine_us",
    "policyengine_canada",
    "policyengine_ng",
    "policyengine_il",
)
COUNTRY_PACKAGE_VERSIONS = {}
for country, package_name in zip(COUNTRIES, COUNTRY_PACKAGE_NAMES):
    try:
        COUNTRY_PACKAGE_VERSIONS[country] = version(package_name)
    except Exception:
        COUNTRY_PACKAGE_VERSIONS[country] = "0.0.0"
__version__ = VERSION
