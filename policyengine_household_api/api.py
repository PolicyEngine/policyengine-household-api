"""
This is the main Flask app for the PolicyEngine API.
"""
# Python imports
import os

# External imports
from flask_cors import CORS
import flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from dotenv import load_dotenv
from authlib.integrations.flask_oauth2 import ResourceProtector

# Internal imports
from .auth.validation import Auth0JWTBearerTokenValidator
from .constants import VERSION
from .data.setup import getconn

# Endpoints
from .endpoints import (
    get_home,
    get_calculate,
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

# Configure database connection
app.config['SQLALCHEMY_DATABASE_URI'] = "mysql+pymysql://"
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "creator": getconn
}

# Configure database schema
class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
db.init_app(app)

# Note that this only updates if table already exists
from policyengine_household_api.data.models import Visits
with app.app_context():
    db.create_all()


app.route("/", methods=["GET"])(get_home)


@app.route("/<country_id>/calculate", methods=["POST"])
@require_auth(None)
def calculate(country_id):
    return get_calculate(country_id)


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


print("API initialised.")
