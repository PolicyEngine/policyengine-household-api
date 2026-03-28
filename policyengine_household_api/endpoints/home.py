import json

from flask import Response


def get_home() -> Response:
    """Return service metadata for self-serve and hosted API users."""

    response_body = {
        "status": "ok",
        "message": "PolicyEngine household API",
        "result": {
            "docs_url": "https://www.policyengine.org/us/api",
            "container_image": "ghcr.io/policyengine/policyengine-household-api",
            "hosted_calculate_url": "https://household.api.policyengine.org/us/calculate",
            "local_calculate_url": "http://localhost:8080/us/calculate",
            "health_checks": {
                "liveness": "/liveness_check",
                "readiness": "/readiness_check",
            },
        },
    }

    return Response(
        json.dumps(response_body),
        status=200,
        mimetype="application/json",
    )
