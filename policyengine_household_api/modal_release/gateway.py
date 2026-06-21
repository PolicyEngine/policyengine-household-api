from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Callable

from flask import Flask, Response, jsonify, request

from policyengine_household_api.constants import COUNTRIES
from policyengine_household_api.observability import (
    OBSERVABILITY_INTERNAL_DISPATCH_HEADER,
    REQUEST_ID_HEADER,
    TRACEPARENT_HEADER,
    current_context,
    traceparent_header,
    init_observability,
    record_error,
    set_attribute,
    segment,
)
from policyengine_household_api.modal_release.manifest import (
    MANIFEST_DICT_KEY,
    MANIFEST_DICT_NAME,
    empty_manifest,
    validate_manifest,
)
from policyengine_household_api.modal_release.routing_metadata import (
    MODAL_ROUTING_PAYLOAD_KEY,
    modal_routing_payload,
)
from policyengine_household_api.version_config import ACTIVE_RELEASE_CHANNELS
from policyengine_household_api.version_routing import (
    UnsupportedVersionError,
    VersionRoutingError,
    active_versions_for_country,
)


VERSIONED_ENDPOINTS = {"calculate", "calculate_demo"}


@dataclass(frozen=True)
class ResolvedApp:
    app_name: str
    requested_version: str
    channel: str


class GatewayResolutionError(VersionRoutingError):
    pass


def create_gateway_app(
    *,
    manifest_loader: Callable[[], dict[str, Any]] | None = None,
    worker_request: Callable[[str, dict[str, Any]], Response] | None = None,
) -> Flask:
    app = Flask(__name__)
    init_observability(app, service_role="modal_gateway")
    load_manifest = manifest_loader or load_modal_manifest
    route_to_worker_function = worker_request or call_worker_function

    @app.get("/liveness_check")
    def liveness_check() -> Response:
        return Response("OK", status=200, mimetype="text/plain")

    @app.get("/readiness_check")
    def readiness_check() -> Response:
        manifest = load_manifest()
        if not validate_manifest(manifest).get("current"):
            return jsonify(
                {
                    "status": "error",
                    "message": "No current household API app is configured",
                }
            ), 503
        return Response("OK", status=200, mimetype="text/plain")

    @app.get("/versions")
    def versions() -> Response:
        return jsonify(validate_manifest(load_manifest()))

    @app.get("/versions/<country_id>")
    def country_versions(country_id: str) -> Response:
        if country_id not in COUNTRIES:
            return _json_error(f"Unsupported country `{country_id}`", 404)

        manifest = validate_manifest(load_manifest())
        country_versions = {}
        for channel in ACTIVE_RELEASE_CHANNELS:
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
    def route_request(path: str) -> Response:
        country_id, endpoint = _country_and_endpoint(path)
        body = request.get_data()
        set_attribute("country_id", country_id)
        set_attribute("endpoint", endpoint)

        try:
            with segment("manifest_load"):
                manifest = validate_manifest(load_manifest())
            with segment("version_resolution"):
                if country_id and endpoint in VERSIONED_ENDPOINTS:
                    body, requested_version = _extract_requested_version(body)
                else:
                    requested_version = "current"
                resolved_app = resolve_app_for_request(
                    manifest,
                    country_id=country_id,
                    requested_version=requested_version,
                )
            set_attribute("backend", "modal")
            set_attribute("modal_app_name", resolved_app.app_name)
            set_attribute(
                "requested_version",
                resolved_app.requested_version,
            )
            set_attribute("resolved_channel", resolved_app.channel)
            with segment("worker_dispatch", backend="modal"):
                return route_to_worker_function(
                    resolved_app.app_name,
                    _request_payload(path, body, resolved_app),
                )
        except VersionRoutingError as e:
            record_error(
                e,
                handled=True,
                status_code=e.status_code,
                include_stack=False,
            )
            return _json_error(
                str(e),
                e.status_code,
                code=e.code,
                requested_version=e.requested_version,
                country_id=e.country_id,
                available_versions=e.available_versions,
            )

    return app


def load_modal_manifest() -> dict[str, Any]:
    import modal
    from modal.exception import NotFoundError

    try:
        manifest_dict = modal.Dict.from_name(
            MANIFEST_DICT_NAME,
            create_if_missing=False,
        )
    except NotFoundError:
        return empty_manifest()
    return validate_manifest(manifest_dict.get(MANIFEST_DICT_KEY))


def resolve_app_for_request(
    manifest: dict[str, Any],
    *,
    country_id: str | None,
    requested_version: str | None,
) -> ResolvedApp:
    requested = requested_version or "current"

    if requested in ACTIVE_RELEASE_CHANNELS:
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

    for channel in ACTIVE_RELEASE_CHANNELS:
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

    available_versions = active_versions_for_country(manifest, country_id)
    raise UnsupportedVersionError(
        country_id=country_id,
        requested_version=requested,
        available_versions=available_versions,
        active_target_label="household API app",
    )


def call_worker_function(app_name: str, payload: dict[str, Any]) -> Response:
    import modal

    # Prefer the class-based worker (post #1528). During the release
    # transition the existing frontier is promoted to current without a
    # redeploy, so for one release cycle the current worker may still expose
    # the pre-#1528 top-level `handle_household_request` function. Fall back
    # to that shape if the class is not present.
    try:
        with segment("modal_worker_lookup", backend="modal"):
            worker_cls = modal.Cls.from_name(app_name, "HouseholdWorker")
        with segment("modal_remote_execution", backend="modal"):
            return _response_from_dispatch_result(
                worker_cls().handle_household_request.remote(payload)
            )
    except modal.exception.NotFoundError:
        with segment("modal_worker_lookup", backend="modal"):
            worker_function = modal.Function.from_name(
                app_name,
                "handle_household_request",
            )
        with segment("modal_remote_execution", backend="modal"):
            return _response_from_dispatch_result(
                worker_function.remote(payload)
            )


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


def _request_payload(
    path: str,
    body: bytes,
    resolved_app: ResolvedApp,
) -> dict[str, Any]:
    return {
        "method": request.method,
        "path": path,
        "query_string": request.query_string.decode("utf-8"),
        "headers": _forward_headers(),
        "body": body,
        MODAL_ROUTING_PAYLOAD_KEY: modal_routing_payload(
            requested_version=resolved_app.requested_version,
            resolved_channel=resolved_app.channel,
        ),
    }


def _forward_headers() -> dict[str, str]:
    forwarded_headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in {"host", "content-length"}
    }
    if request.content_type:
        forwarded_headers["Content-Type"] = request.content_type
    context = current_context()
    if context is not None:
        forwarded_headers[REQUEST_ID_HEADER] = context.request_id
        forwarded_headers[OBSERVABILITY_INTERNAL_DISPATCH_HEADER] = "1"
    traceparent = traceparent_header()
    if traceparent:
        forwarded_headers[TRACEPARENT_HEADER] = traceparent
    return forwarded_headers


def _response_from_dispatch_result(result: dict[str, Any]) -> Response:
    body = result.get("body", b"")
    if isinstance(body, str):
        body = body.encode("utf-8")
    return Response(
        body,
        status=int(result["status_code"]),
        headers=list(result.get("headers") or []),
    )


def _json_error(
    message: str,
    status: int,
    *,
    code: str | None = None,
    requested_version: str | None = None,
    country_id: str | None = None,
    available_versions: dict[str, str] | None = None,
) -> Response:
    payload: dict[str, Any] = {"status": "error", "message": message}
    if code is not None:
        payload["code"] = code
    if requested_version is not None:
        payload["requested_version"] = requested_version
    if country_id is not None:
        payload["country_id"] = country_id
    if available_versions is not None:
        payload["available_versions"] = available_versions
    response = jsonify(payload)
    response.status_code = status
    return response
