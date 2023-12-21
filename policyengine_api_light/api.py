"""
This is the main Flask app for the PolicyEngine API.
"""
from flask_cors import CORS
import flask
from .constants import VERSION

# Endpoints
from .endpoints import (
    get_home,
    get_calculate,
)

print("Initialising API...")

app = application = flask.Flask(__name__)

CORS(app)

app.route("/", methods=["GET"])(get_home)

app.route("/<country_id>/calculate", methods=["POST"])(get_calculate)


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
