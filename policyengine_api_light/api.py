"""
This is the main Flask app for the PolicyEngine API.
"""
from flask_cors import CORS
import flask
from .constants import VERSION

# from werkzeug.middleware.profiler import ProfilerMiddleware

# Endpoints

from .endpoints import (
    get_home,
    get_metadata,
    get_calculate,
    get_search,
)

print("Initialising API...")

app = application = flask.Flask(__name__)

CORS(app)

app.route("/", methods=["GET"])(get_home)

app.route("/<country_id>/metadata", methods=["GET"])(get_metadata)

app.route("/<country_id>/calculate", methods=["POST"])(
    (get_calculate)
)

app.route("/<country_id>/calculate-full", methods=["POST"])(
  (
    lambda *args, **kwargs: get_calculate(
      *args, **kwargs, add_missing=True
    )
  )
)

app.route("/<country_id>/search", methods=["GET"])(get_search)

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


# Add OpenAPI spec (__file__.parent / openapi_spec.yaml)

# with open(Path(__file__).parent / "openapi_spec.yaml", encoding="utf-8") as f:
#     openapi_spec = yaml.safe_load(f)
#     openapi_spec["info"]["version"] = VERSION


# @app.route("/specification", methods=["GET"])
# def get_specification():
#     return flask.jsonify(openapi_spec)


print("API initialised.")
