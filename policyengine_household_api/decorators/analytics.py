"""
Optional analytics decorator that only logs if analytics is enabled.
This decorator checks configuration before attempting to log analytics data.
"""

from functools import wraps
from flask import request
from datetime import datetime
import jwt
import logging
from policyengine_household_api.constants import VERSION

logger = logging.getLogger(__name__)


def log_analytics_if_enabled(func):
    """
    Decorator that logs analytics only if analytics is enabled in configuration.

    This decorator:
    1. Checks if analytics is enabled
    2. If disabled, passes through without logging
    3. If enabled, logs the visit to the database
    """

    @wraps(func)
    def decorated_function(*args, **kwargs):
        # Check if analytics is enabled
        try:
            from policyengine_household_api.data.analytics_setup import (
                is_analytics_enabled,
            )

            if not is_analytics_enabled():
                # Analytics disabled, just execute the function
                return func(*args, **kwargs)
        except Exception as e:
            logger.debug(f"Could not determine analytics status: {e}")
            # If we can't determine status, proceed without analytics
            return func(*args, **kwargs)

        # Analytics is enabled, proceed with logging
        try:
            from policyengine_household_api.api import db
            from policyengine_household_api.data.models import Visit

            # Create a record that will be emitted to the db
            new_visit = Visit()

            # Pull client_id from JWT
            try:
                auth_header = str(request.authorization)
                token = auth_header.split(" ")[1]
                decoded_token = jwt.decode(
                    token, options={"verify_signature": False}
                )
                client_id = decoded_token["sub"]
                suffix_to_slice = "@clients"
                if (
                    len(client_id) >= len(suffix_to_slice)
                    and client_id[-len(suffix_to_slice) :] == suffix_to_slice
                ):
                    client_id = client_id[: -len(suffix_to_slice)]
                new_visit.client_id = client_id
            except Exception as e:
                logger.debug(f"Could not extract client_id from JWT: {e}")
                new_visit.client_id = "unknown"

            # Set API version
            new_visit.api_version = VERSION

            # Set endpoint and method
            new_visit.endpoint = request.endpoint
            new_visit.method = request.method

            # Set content_length_bytes
            new_visit.content_length_bytes = request.content_length

            # Set the date and time
            now = datetime.utcnow()
            new_visit.datetime = now

            # Emit the new record to the db
            db.session.add(new_visit)
            db.session.commit()

        except Exception as e:
            # Log the error but don't fail the request
            logger.error(f"Failed to log analytics: {e}")

        return func(*args, **kwargs)

    return decorated_function
