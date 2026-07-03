import tomllib
from pathlib import Path
from importlib.metadata import PackageNotFoundError, version

REPO = Path(__file__).parents[1]
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


def get_repo_version() -> str:
    pyproject = REPO / "pyproject.toml"
    try:
        project = tomllib.loads(pyproject.read_text())["project"]
        return project["version"]
    except (FileNotFoundError, KeyError, tomllib.TOMLDecodeError):
        try:
            return version("policyengine-household-api")
        except PackageNotFoundError:
            return "0.0.0"


VERSION = get_repo_version()
COUNTRY_PACKAGE_VERSIONS = {
    country: get_package_version(package_name)
    for country, package_name in zip(COUNTRIES, COUNTRY_PACKAGE_NAMES)
}
__version__ = VERSION
