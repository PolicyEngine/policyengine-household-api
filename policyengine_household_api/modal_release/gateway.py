from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import Flask, Response, jsonify, request

from policyengine_household_api.constants import COUNTRIES
from policyengine_household_api.modal_release.manifest import (
    MANIFEST_DICT_KEY,
    MANIFEST_DICT_NAME,
    normalize_manifest,
)


VERSIONED_ENDPOINTS = {"calculate", "calculate_demo", "ai-analysis"}


@dataclass(frozen=True)
class ResolvedApp:
    app_name: str
    requested_version: str
    channel: str


class GatewayResolutionError(ValueError):
    pass


def create_gateway_app(
    *,
    manifest_loader: Callable[[], dict[str, Any]] | None = None,
    proxy_request: Callable[[str, bytes], Response] | None = None,
) -> Flask:
    app = Flask(__name__)
    load_manifest = manifest_loader or load_modal_manifest
    proxy = proxy_request or proxy_to_worker

    @app.get("/liveness_check")
    def liveness_check() -> Response:
        return Response("OK", status=200, mimetype="text/plain")

    @app.get("/readiness_check")
    def readiness_check() -> Response:
        manifest = load_manifest()
        if not normalize_manifest(manifest).get("current"):
            return jsonify(
                {
                    "status": "error",
                    "message": "No current household API app is configured",
                }
            ), 503
        return Response("OK", status=200, mimetype="text/plain")

    @app.get("/versions")
    def versions() -> Response:
        return jsonify(normalize_manifest(load_manifest()))

    @app.get("/versions/<country_id>")
    def country_versions(country_id: str) -> Response:
        if country_id not in COUNTRIES:
            return _json_error(f"Unsupported country `{country_id}`", 404)

        manifest = normalize_manifest(load_manifest())
        country_versions = {}
        for channel in ("current", "frontier"):
            app_reference = manifest.get(channel)
            if not app_reference:
                continue
            country_versions[channel] = app_reference["package_versions"].get(
                country_id
            )
        return jsonify(country_versions)

    @app.route(
        "/",
        defaults={"path": ""},
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    )
    @app.route(
        "/<path:path>",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    )
    def route_to_worker(path: str) -> Response:
        manifest = normalize_manifest(load_manifest())
        country_id, endpoint = _country_and_endpoint(path)
        body = request.get_data()

        try:
            if country_id and endpoint in VERSIONED_ENDPOINTS:
                body, requested_version = _extract_requested_version(body)
                resolved_app = resolve_app_for_request(
                    manifest,
                    country_id=country_id,
                    requested_version=requested_version,
                )
            else:
                resolved_app = resolve_app_for_request(
                    manifest,
                    country_id=country_id,
                    requested_version="current",
                )
        except GatewayResolutionError as e:
            return _json_error(str(e), 400)

        return proxy(resolved_app.app_name, body)

    return app


def load_modal_manifest() -> dict[str, Any]:
    import modal

    manifest_dict = modal.Dict.from_name(
        MANIFEST_DICT_NAME,
        create_if_missing=True,
    )
    return normalize_manifest(manifest_dict.get(MANIFEST_DICT_KEY))


def resolve_app_for_request(
    manifest: dict[str, Any],
    *,
    country_id: str | None,
    requested_version: str | None,
) -> ResolvedApp:
    requested = requested_version or "current"

    if requested in {"current", "frontier"}:
        app_reference = manifest.get(requested)
        if not app_reference:
            raise GatewayResolutionError(
                f"No `{requested}` household API version is available"
            )
        return ResolvedApp(
            app_name=app_reference["app_name"],
            requested_version=requested,
            channel=requested,
        )

    if not country_id:
        raise GatewayResolutionError(
            "Exact package version routing requires a country endpoint"
        )

    for channel in ("current", "frontier"):
        app_reference = manifest.get(channel)
        if not app_reference:
            continue
        package_version = app_reference["package_versions"].get(country_id)
        if package_version == requested:
            return ResolvedApp(
                app_name=app_reference["app_name"],
                requested_version=requested,
                channel=channel,
            )

    raise GatewayResolutionError(
        f"No active household API app serves `{country_id}` package "
        f"version `{requested}`"
    )


def proxy_to_worker(app_name: str, body: bytes) -> Response:
    worker_url = _worker_url(app_name)
    upstream_request = Request(
        f"{worker_url}{request.full_path}",
        data=body if request.method != "GET" else None,
        method=request.method,
        headers=_worker_headers(),
    )

    try:
        with urlopen(upstream_request, timeout=120) as upstream_response:
            return _response_from_upstream(upstream_response)
    except HTTPError as e:
        return _response_from_upstream(e)
    except URLError as e:
        return _json_error(f"Unable to reach household API worker: {e}", 502)


def _extract_requested_version(body: bytes) -> tuple[bytes, str]:
    if not body:
        return body, "current"

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return body, "current"

    if not isinstance(payload, dict):
        return body, "current"

    requested_version = payload.pop("version", "current") or "current"
    if not isinstance(requested_version, str):
        raise GatewayResolutionError("`version` must be a string")

    return json.dumps(payload).encode("utf-8"), requested_version


def _country_and_endpoint(path: str) -> tuple[str | None, str | None]:
    parts = [part for part in path.split("/") if part]
    if len(parts) < 2 or parts[0] not in COUNTRIES:
        return None, None
    return parts[0], parts[1]


def _worker_headers() -> dict[str, str]:
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in {"host", "content-length"}
    }
    gateway_secret = os.getenv("HOUSEHOLD_MODAL_GATEWAY_SECRET")
    if gateway_secret:
        headers["X-Household-Modal-Gateway-Secret"] = gateway_secret
    if request.content_type:
        headers["Content-Type"] = request.content_type
    return headers


def _worker_url(app_name: str) -> str:
    workspace = os.getenv("MODAL_WORKSPACE", "policyengine")
    environment = os.getenv("MODAL_ENVIRONMENT", "main")
    if environment == "main":
        host = f"{workspace}--{app_name}-web-app.modal.run"
    else:
        host = f"{workspace}-{environment}--{app_name}-web-app.modal.run"
    return f"https://{host}"


def _response_from_upstream(upstream_response) -> Response:
    content = upstream_response.read()
    headers = [
        (key, value)
        for key, value in upstream_response.headers.items()
        if key.lower()
        not in {
            "content-encoding",
            "content-length",
            "connection",
            "transfer-encoding",
        }
    ]
    return Response(
        content,
        status=upstream_response.status,
        headers=headers,
    )


def _json_error(message: str, status: int) -> Response:
    response = jsonify({"status": "error", "message": message})
    response.status_code = status
    return response
