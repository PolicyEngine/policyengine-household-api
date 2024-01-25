from functools import wraps
from flask import request
from datetime import date, time

from policyengine_household_api.data.models import Visit

def log_analytics(func):
  @wraps(func)
  def decorated_function(*args, **kwargs):
    
    
    # Create a record that will be emitted to the db
    new_visit = Visit()

    # Pull client_id from JWT

    # Set API version

    # Set endpoint and method

    # Set content_length_bytes

    # Set the date and time

    return func(*args, **kwargs)
  return decorated_function