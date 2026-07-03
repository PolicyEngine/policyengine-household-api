"""Utility helpers for the Household API.

Keep this package import lightweight. Heavy submodules (`json` pulls numpy)
must be imported directly, e.g.
`from policyengine_household_api.utils.json import get_safe_json`.

The config loader moved to `policyengine_household_common.config_loader`;
the re-exports below preserve the public
`from policyengine_household_api.utils import get_config_value` surface.
"""

from policyengine_household_common import config_loader
from policyengine_household_common.config_loader import (
    ConfigLoader,
    get_config,
    get_config_value,
)

__all__ = [
    "config_loader",
    "ConfigLoader",
    "get_config",
    "get_config_value",
]
