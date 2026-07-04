# Re-export shim: the analytics models moved to the common lib. Kept for one
# release cycle so external `policyengine_household_api.models.analytics`
# imports keep working.
from policyengine_household_common.models.analytics import *  # noqa: F401,F403
