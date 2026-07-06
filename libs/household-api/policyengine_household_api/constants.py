import tomllib
from pathlib import Path
from importlib.metadata import PackageNotFoundError, version

# Shared constants live in the common lib; re-exported here because this
# module is part of the published package's public surface.
from policyengine_household_common.constants import (  # noqa: F401
    COUNTRIES,
    COUNTRY_PACKAGE_NAMES,
    COUNTRY_PACKAGE_VERSIONS,
    GET,
    LIST,
    POST,
    UPDATE,
    get_package_version,
)

REPO = Path(__file__).parents[1]


def get_repo_version() -> str:
    # VERSION stays in this package (not the common lib): it is the version
    # of the published policyengine-household-api distribution, resolved from
    # the member pyproject.toml sitting one level above this package, with an
    # installed-distribution fallback.
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
__version__ = VERSION
