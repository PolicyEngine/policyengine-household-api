"""Utility helpers for the Household API.

Keep this package import lightweight: the Cloud Run analytics writer imports
`policyengine_household_api.utils.config_loader`, which executes this module
first. Heavy submodules (`json` pulls numpy) must be imported directly, e.g.
`from policyengine_household_api.utils.json import get_safe_json`.
"""

from . import config_loader
from .config_loader import ConfigLoader, get_config, get_config_value

__all__ = [
    "config_loader",
    "ConfigLoader",
    "get_config",
    "get_config_value",
]
