from werkzeug.wrappers import Request
from datetime import date, time

from policyengine_household_api.data.models import Visit

class AnalyticsWrapper:
  def __init__(self, app):
    self.app = app

  def __call__(self, environ, start_response):
    request = Request(environ)

    # Create a record that will be emitted to the db
    new_visit = Visit()

    # Attempt to pull the client_id from the request's auth header 
      # If the request isn't properly authenticated, set client_id to
      # "invalid"

    # Set API version

    # Set endpoint and method

    # Set content_length_bytes

    # Set the date and time

    return self.app(environ, start_response)