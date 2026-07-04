from importlib.metadata import PackageNotFoundError, version

GET = "GET"
POST = "POST"
UPDATE = "UPDATE"
LIST = "LIST"
COUNTRIES = ("uk", "us", "ca", "ng", "il")
COUNTRY_PACKAGE_NAMES = (
    "policyengine_uk",
    "policyengine_us",
    "policyengine_canada",
    "policyengine_ng",
    "policyengine_il",
)


def get_package_version(package_name: str) -> str:
    try:
        return version(package_name)
    except PackageNotFoundError:
        return "0.0.0"


COUNTRY_PACKAGE_VERSIONS = {
    country: get_package_version(package_name)
    for country, package_name in zip(COUNTRIES, COUNTRY_PACKAGE_NAMES)
}
