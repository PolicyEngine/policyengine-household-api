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
from authlib.integrations.flask_oauth2 import ResourceProtector
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Internal imports
from .auth.validation import Auth0JWTBearerTokenValidator
from .constants import VERSION, REPO
from .data.setup import getconn

# Endpoints
from .endpoints import (
    get_home,
    get_calculate,
    generate_ai_explainer,
)

# Configure authentication
load_dotenv()
require_auth = ResourceProtector()
validator = Auth0JWTBearerTokenValidator(
    os.getenv("AUTH0_ADDRESS_NO_DOMAIN"), os.getenv("AUTH0_AUDIENCE_NO_DOMAIN")
)
require_auth.register_token_validator(validator)


print("Initialising API...")

app = application = flask.Flask(__name__)

CORS(app)

# Initialize rate limiter
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per hour"]
)

# Configure database connection
if os.getenv("FLASK_DEBUG") == "1":
    db_url = REPO / "policyengine_household_api" / "data" / "policyengine.db"
    if Path(db_url).exists():
        Path(db_url).unlink()
    if not Path(db_url).exists():
        Path(db_url).touch()
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:////" + str(db_url)
else:
    app.config["SQLALCHEMY_DATABASE_URI"] = "mysql+pymysql://"
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"creator": getconn}


# Configure database schema
class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)
db.init_app(app)

# Note that this only updates if table already exists
from policyengine_household_api.data.models import Visit

with app.app_context():
    db.create_all()

from policyengine_household_api.decorators.analytics import log_analytics

app.route("/", methods=["GET"])(get_home)


@app.route("/<country_id>/calculate", methods=["POST"])
@require_auth(None)
@log_analytics
def calculate(country_id):
    return get_calculate(country_id)


@app.route("/<country_id>/ai-analysis", methods=["POST"])
@require_auth(None)
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


@app.route("/<country_id>/calculate_demo", methods=["POST"])
@limiter.limit("1 per second")
def calculate_demo(country_id):
    return get_calculate(country_id)


print("API initialised.")
