from functools import wraps
from flask import request
from datetime import datetime
import jwt
from policyengine_household_api.constants import VERSION
from policyengine_household_api.api import db

from policyengine_household_api.data.models import Visit


def log_analytics(func):
    @wraps(func)
    def decorated_function(*args, **kwargs):
        # Create a record that will be emitted to the db
        new_visit = Visit()

        # Pull client_id from JWT
        auth_header = str(request.authorization)
        token = auth_header.split(" ")[1]
        decoded_token = jwt.decode(token, options={"verify_signature": False})
        client_id = decoded_token["sub"]
        suffix_to_slice = "@clients"
        if (
            len(client_id) >= len(suffix_to_slice)
            and client_id[-len(suffix_to_slice) :] == suffix_to_slice
        ):
            client_id = client_id[: -len(suffix_to_slice)]
        new_visit.client_id = client_id

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

        return func(*args, **kwargs)

    return decorated_function
