"""
This is the main Flask app for the PolicyEngine API.
"""

# Python imports
import os
from pathlib import Path

# External imports
from flask_cors import CORS
import flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from dotenv import load_dotenv
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from policyengine_household_api.data.analytics_setup import (
    initialize_analytics_db_if_enabled,
)

# Internal imports
from .decorators.auth import create_auth_decorator
from .constants import VERSION, REPO
from policyengine_household_api.decorators.analytics import (
    log_analytics_if_enabled,
)
from policyengine_household_api.utils.config_loader import get_config_value

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


def _resolve_cors_origins():
    """
    Resolve the CORS allowed origins list.

    Priority:
      1. CORS_ALLOWED_ORIGINS env var (comma-separated list)
      2. config value "cors.allowed_origins" (list or comma string)
      3. Safe default: the PolicyEngine production domains

    Use regex patterns so that wildcard subdomains work with
    Flask-CORS's `origins` kwarg.
    """
    raw = os.getenv("CORS_ALLOWED_ORIGINS") or get_config_value(
        "cors.allowed_origins", None
    )

    if raw is None:
        # Flask-CORS uses re.match, which is a prefix match; anchor with
        # ``$`` so a hostile host like ``policyengine.org.attacker.com``
        # cannot satisfy the wildcard pattern. Include ``localhost:*``
        # so local dev servers can hit the API without extra setup.
        origins = [
            "https://policyengine.org",
            r"https://.*\.policyengine\.org$",
            r"http://localhost(:[0-9]+)?$",
            r"http://127\.0\.0\.1(:[0-9]+)?$",
        ]
    elif isinstance(raw, str):
        origins = [o.strip() for o in raw.split(",") if o.strip()]
    else:
        origins = list(raw)

    return origins


CORS(app, origins=_resolve_cors_origins())

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
