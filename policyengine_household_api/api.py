"""
This is the main Flask app for the PolicyEngine API.
"""

# Python imports
import os

# External imports
from flask_cors import CORS
import flask
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from policyengine_household_api.data.analytics_setup import (
    initialize_analytics_db_if_enabled,
)

# Internal imports
from .decorators.auth import create_auth_decorator
from policyengine_household_api.decorators.analytics import (
    log_analytics_if_enabled,
)

# Endpoints
from .endpoints import (
    get_home,
    get_calculate,
    generate_ai_explainer,
)

# Create the authentication decorator (will be either Auth0 or no-op based on config)
require_auth_if_enabled = create_auth_decorator()


print("Initialising API...")

app = application = flask.Flask(__name__)

# Reject absurdly large request bodies before any view runs. 10 MiB is
# well above the largest legitimate household payload we have seen
# (axes scans push a few hundred KiB) while still capping the memory a
# single attacker can force us to allocate. Overridable via the
# ``MAX_CONTENT_LENGTH`` env var (bytes).
app.config["MAX_CONTENT_LENGTH"] = int(
    os.getenv("MAX_CONTENT_LENGTH", 10 * 1024 * 1024)
)

CORS(app)

# Use in-memory storage for rate limiting
# Note that this provides limits per-instance;
# rate limits not shared if scaling more than 1 instance.
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=[],
    storage_uri="memory://",
)

initialize_analytics_db_if_enabled(app)

app.route("/", methods=["GET"])(get_home)


@app.route("/<country_id>/calculate", methods=["POST"])
@require_auth_if_enabled()
@limiter.limit("60 per minute")
@log_analytics_if_enabled
def calculate(country_id):
    return get_calculate(country_id)


@app.route("/<country_id>/ai-analysis", methods=["POST"])
@require_auth_if_enabled()
def ai_analysis(country_id: str):
    return generate_ai_explainer(country_id)


@app.route("/liveness_check", methods=["GET"])
def liveness_check():
    return flask.Response(
        "OK", status=200, headers={"Content-Type": "text/plain"}
    )


@app.route("/readiness_check", methods=["GET"])
def readiness_check():
    return flask.Response(
        "OK", status=200, headers={"Content-Type": "text/plain"}
    )


# Note: `/calculate_demo` is intentionally public (documented in
# config/README.md). It is guarded by a conservative rate limit rather
# than JWT authentication.
@app.route("/<country_id>/calculate_demo", methods=["POST"])
@limiter.limit("1 per 10 seconds")
def calculate_demo(country_id):
    return get_calculate(country_id)


print("API initialised.")
