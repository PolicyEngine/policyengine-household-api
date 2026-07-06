# Re-export shim: the config loader moved to the common lib. Kept for one
# release cycle so external `policyengine_household_api.utils.config_loader`
# imports keep working.
from policyengine_household_common.config_loader import *  # noqa: F401,F403
from policyengine_household_common.config_loader import (  # noqa: F401
    ConfigLoader,
    get_config,
    get_config_value,
)
