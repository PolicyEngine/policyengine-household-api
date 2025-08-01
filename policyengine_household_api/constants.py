from pathlib import Path
import pkg_resources

REPO = Path(__file__).parents[1]
GET = "GET"
POST = "POST"
UPDATE = "UPDATE"
LIST = "LIST"
VERSION = "0.7.1"
COUNTRIES = ("uk", "us", "ca", "ng", "il")
COUNTRY_PACKAGE_NAMES = (
    "policyengine_uk",
    "policyengine_us",
    "policyengine_canada",
    "policyengine_ng",
    "policyengine_il",
)
try:
    COUNTRY_PACKAGE_VERSIONS = {
        country: pkg_resources.get_distribution(package_name).version
        for country, package_name in zip(COUNTRIES, COUNTRY_PACKAGE_NAMES)
    }
except:
    COUNTRY_PACKAGE_VERSIONS = {country: "0.0.0" for country in COUNTRIES}
__version__ = VERSION
