from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import os
import threading
import time
from typing import Any, Callable
from urllib import error, request as urllib_request

from flask import Flask, Response, jsonify, request
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import id_token

from policyengine_household_api.constants import COUNTRIES
from policyengine_household_api.failover.dispatch_codec import (
    decode_dispatch_response,
    encode_dispatch_request,
)
from policyengine_household_api.failover.manifest import (
    FAILOVER_MANIFEST_BLOB_ENV,
    FAILOVER_MANIFEST_BUCKET_ENV,
    FailoverManifestError,
    ResolvedFailoverChannel,
    resolve_failover_channel_for_request,
    validate_failover_manifest,
)
from policyengine_household_api.modal_release.gateway import (
    VERSIONED_ENDPOINTS,
    _country_and_endpoint,
    _extract_requested_version,
    _json_error,
    _request_payload,
    _response_from_dispatch_result,
)


LOGGER = logging.getLogger(__name__)
MODAL_STATUS_URL = "https://status.modal.com/index.json"
FORCE_BACKEND_ENV = "HOUSEHOLD_FAILOVER_FORCE_BACKEND"
RETRY_AFTER_SECONDS = 10
MODAL_FAILURE_THRESHOLD = 3
MODAL_PROBE_INTERVAL_SECONDS = 15
MODAL_STATUS_CHECK_MIN_INTERVAL_SECONDS = 60
MANIFEST_CACHE_SECONDS = 30


class ModalBackendUnavailable(RuntimeError):
    pass


class FallbackBackendUnavailable(RuntimeError):
    pass


@dataclass
class ChannelCircuit:
    consecutive_failures: int = 0
    is_open: bool = False
    last_probe_at: float = 0.0
    last_modal_status_check_at: float = 0.0


class CircuitRegistry:
    def __init__(
        self,
        *,
        time_source: Callable[[], float] | None = None,
    ) -> None:
        self._time = time_source or time.monotonic
        self._circuits = {
            "current": ChannelCircuit(),
            "frontier": ChannelCircuit(),
        }
        self._lock = threading.Lock()

    def state(self, channel: str) -> ChannelCircuit:
        with self._lock:
            return self._circuits[channel]

    def primary_state(self, channel: str) -> str:
        return "unhealthy" if self.state(channel).is_open else "healthy"

    def should_probe(self, channel: str) -> bool:
        circuit = self.state(channel)
        return (
            self._time() - circuit.last_probe_at
            >= MODAL_PROBE_INTERVAL_SECONDS
        )

    def record_probe_attempt(self, channel: str) -> None:
        with self._lock:
            self._circuits[channel].last_probe_at = self._time()

    def record_success(self, channel: str) -> None:
        with self._lock:
            circuit = self._circuits[channel]
            circuit.consecutive_failures = 0
            circuit.is_open = False

    def record_failure(self, channel: str) -> bool:
        with self._lock:
            circuit = self._circuits[channel]
            circuit.consecutive_failures += 1
            if circuit.consecutive_failures >= MODAL_FAILURE_THRESHOLD:
                circuit.is_open = True
            return circuit.is_open

    def should_check_modal_status(self, channel: str) -> bool:
        with self._lock:
            circuit = self._circuits[channel]
            if not circuit.is_open:
                return False
            return (
                self._time() - circuit.last_modal_status_check_at
                >= MODAL_STATUS_CHECK_MIN_INTERVAL_SECONDS
            )

    def record_modal_status_check(self, channel: str) -> None:
        with self._lock:
            self._circuits[channel].last_modal_status_check_at = self._time()


class GcsFailoverManifestLoader:
    def __init__(
        self,
        *,
        bucket_name: str | None = None,
        blob_name: str | None = None,
        cache_seconds: int = MANIFEST_CACHE_SECONDS,
        time_source: Callable[[], float] | None = None,
    ) -> None:
        self.bucket_name = bucket_name or os.getenv(
            FAILOVER_MANIFEST_BUCKET_ENV
        )
        self.blob_name = blob_name or os.getenv(
            FAILOVER_MANIFEST_BLOB_ENV,
            "failover-manifest.json",
        )
        self.cache_seconds = cache_seconds
        self._time = time_source or time.monotonic
        self._cached_manifest: dict[str, Any] | None = None
        self._cached_at = 0.0

    def __call__(self) -> dict[str, Any]:
        if self._cached_manifest and (
            self._time() - self._cached_at < self.cache_seconds
        ):
            return self._cached_manifest
        if not self.bucket_name:
            raise FailoverManifestError(
                f"{FAILOVER_MANIFEST_BUCKET_ENV} must be set"
            )

        from google.cloud import storage

        client = storage.Client()
        blob = client.bucket(self.bucket_name).blob(self.blob_name)
        manifest = validate_failover_manifest(
            json.loads(blob.download_as_text())
        )
        self._cached_manifest = manifest
        self._cached_at = self._time()
        return manifest


def create_gateway_app(
    *,
    manifest_loader: Callable[[], dict[str, Any]] | None = None,
    modal_request: Callable[[str, dict[str, Any]], Response] | None = None,
    modal_health_probe: Callable[[str], None] | None = None,
    fallback_request: (
        Callable[[ResolvedFailoverChannel, dict[str, Any]], Response] | None
    ) = None,
    modal_status_checker: Callable[[], dict[str, Any]] | None = None,
    fallback_warmup: Callable[[ResolvedFailoverChannel], None] | None = None,
    circuit_registry: CircuitRegistry | None = None,
) -> Flask:
    app = Flask(__name__)
    load_manifest = manifest_loader or GcsFailoverManifestLoader()
    call_modal = modal_request or call_modal_worker
    probe_modal = modal_health_probe or probe_modal_worker
    call_fallback = fallback_request or call_cloud_run_worker
    check_modal_status = modal_status_checker or fetch_modal_status
    warm_fallback = fallback_warmup or warm_cloud_run_worker
    circuits = circuit_registry or CircuitRegistry()

    @app.get("/liveness_check")
    def liveness_check() -> Response:
        return Response("OK", status=200, mimetype="text/plain")

    @app.get("/readiness_check")
    def readiness_check() -> Response:
        manifest = validate_failover_manifest(load_manifest())
        if not manifest["channels"].get("current"):
            response = jsonify(
                {
                    "status": "error",
                    "message": "No current failover channel is configured",
                }
            )
            response.status_code = 503
            response.headers["Retry-After"] = str(RETRY_AFTER_SECONDS)
            return response
        return Response("OK", status=200, mimetype="text/plain")

    @app.get("/versions")
    def versions() -> Response:
        return jsonify(validate_failover_manifest(load_manifest()))

    @app.get("/versions/<country_id>")
    def country_versions(country_id: str) -> Response:
        if country_id not in COUNTRIES:
            return _json_error(f"Unsupported country `{country_id}`", 404)

        manifest = validate_failover_manifest(load_manifest())
        versions_by_channel = {}
        for channel, reference in manifest["channels"].items():
            if reference:
                versions_by_channel[channel] = reference[
                    "package_versions"
                ].get(country_id)
        return jsonify(versions_by_channel)

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

        try:
            manifest = validate_failover_manifest(load_manifest())
            if country_id and endpoint in VERSIONED_ENDPOINTS:
                body, requested_version = _extract_requested_version(body)
            else:
                requested_version = "current"
            resolved = resolve_failover_channel_for_request(
                manifest,
                country_id=country_id,
                requested_version=requested_version,
            )
            payload = _request_payload(path, body, resolved)
            response, backend = _route_to_backend(
                resolved,
                payload,
                circuits=circuits,
                call_modal=call_modal,
                probe_modal=probe_modal,
                call_fallback=call_fallback,
                check_modal_status=check_modal_status,
                warm_fallback=warm_fallback,
            )
            return _with_gateway_headers(
                response,
                backend=backend,
                channel=resolved.channel,
                primary_state=circuits.primary_state(resolved.channel),
            )
        except FailoverManifestError as exc:
            return _json_error(str(exc), 400)

    return app


def call_modal_worker(app_name: str, payload: dict[str, Any]) -> Response:
    try:
        from policyengine_household_api.modal_release.gateway import (
            call_worker_function,
        )

        return call_worker_function(app_name, payload)
    except Exception as exc:
        raise ModalBackendUnavailable(str(exc)) from exc


def probe_modal_worker(app_name: str) -> None:
    try:
        import modal

        worker_cls = modal.Cls.from_name(app_name, "HouseholdWorker")
        result = worker_cls().health_check.remote()
    except Exception as exc:
        raise ModalBackendUnavailable(str(exc)) from exc
    if not isinstance(result, dict) or result.get("status") != "ok":
        raise ModalBackendUnavailable("Modal worker health check failed")


def call_cloud_run_worker(
    resolved: ResolvedFailoverChannel,
    payload: dict[str, Any],
) -> Response:
    dispatch_url = _join_url(
        resolved.cloud_run_worker_url,
        "/_internal/dispatch",
    )
    body = json.dumps(encode_dispatch_request(payload)).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        **_cloud_run_auth_header(resolved.cloud_run_worker_url),
    }
    req = urllib_request.Request(
        dispatch_url,
        data=body,
        headers=headers,
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=180) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except (
        OSError,
        error.HTTPError,
        error.URLError,
        json.JSONDecodeError,
    ) as exc:
        raise FallbackBackendUnavailable(str(exc)) from exc
    return _response_from_dispatch_result(
        decode_dispatch_response(response_payload)
    )


def warm_cloud_run_worker(resolved: ResolvedFailoverChannel) -> None:
    health_url = _join_url(resolved.cloud_run_worker_url, "/_internal/health")
    headers = _cloud_run_auth_header(resolved.cloud_run_worker_url)
    req = urllib_request.Request(health_url, headers=headers, method="GET")
    try:
        urllib_request.urlopen(req, timeout=5).close()
    except OSError:
        LOGGER.info("Cloud Run fallback warmup failed", exc_info=True)


def fetch_modal_status() -> dict[str, Any]:
    with urllib_request.urlopen(MODAL_STATUS_URL, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _route_to_backend(
    resolved: ResolvedFailoverChannel,
    payload: dict[str, Any],
    *,
    circuits: CircuitRegistry,
    call_modal: Callable[[str, dict[str, Any]], Response],
    probe_modal: Callable[[str], None],
    call_fallback: Callable[
        [ResolvedFailoverChannel, dict[str, Any]], Response
    ],
    check_modal_status: Callable[[], dict[str, Any]],
    warm_fallback: Callable[[ResolvedFailoverChannel], None],
) -> tuple[Response, str]:
    force_backend = os.getenv(FORCE_BACKEND_ENV, "").strip().lower()
    if force_backend == "cloud_run":
        return call_fallback(resolved, payload), "cloud_run"

    if force_backend != "modal":
        _refresh_modal_circuit(
            resolved,
            circuits=circuits,
            probe_modal=probe_modal,
            check_modal_status=check_modal_status,
            warm_fallback=warm_fallback,
        )
        if circuits.state(resolved.channel).is_open:
            return _route_to_fallback_or_503(
                resolved,
                payload,
                call_fallback=call_fallback,
            )

    try:
        response = call_modal(resolved.modal_app_name, payload)
        circuits.record_success(resolved.channel)
        return response, "modal"
    except ModalBackendUnavailable:
        if circuits.record_failure(resolved.channel):
            _check_modal_status_after_open(
                resolved.channel,
                circuits=circuits,
                check_modal_status=check_modal_status,
            )
            warm_fallback(resolved)
            return _route_to_fallback_or_503(
                resolved,
                payload,
                call_fallback=call_fallback,
            )
        return _backend_unavailable_response(resolved), "none"


def _refresh_modal_circuit(
    resolved: ResolvedFailoverChannel,
    *,
    circuits: CircuitRegistry,
    probe_modal: Callable[[str], None],
    check_modal_status: Callable[[], dict[str, Any]],
    warm_fallback: Callable[[ResolvedFailoverChannel], None],
) -> None:
    if not circuits.should_probe(resolved.channel):
        return
    circuits.record_probe_attempt(resolved.channel)
    try:
        probe_modal(resolved.modal_app_name)
        circuits.record_success(resolved.channel)
    except ModalBackendUnavailable:
        if circuits.record_failure(resolved.channel):
            _check_modal_status_after_open(
                resolved.channel,
                circuits=circuits,
                check_modal_status=check_modal_status,
            )
            warm_fallback(resolved)


def _route_to_fallback_or_503(
    resolved: ResolvedFailoverChannel,
    payload: dict[str, Any],
    *,
    call_fallback: Callable[
        [ResolvedFailoverChannel, dict[str, Any]], Response
    ],
) -> tuple[Response, str]:
    try:
        return call_fallback(resolved, payload), "cloud_run"
    except FallbackBackendUnavailable:
        return _backend_unavailable_response(resolved), "none"


def _check_modal_status_after_open(
    channel: str,
    *,
    circuits: CircuitRegistry,
    check_modal_status: Callable[[], dict[str, Any]],
) -> None:
    if not circuits.should_check_modal_status(channel):
        return
    circuits.record_modal_status_check(channel)
    try:
        LOGGER.warning(
            "Modal circuit opened; status page snapshot: %s",
            check_modal_status(),
        )
    except Exception:
        LOGGER.warning("Modal status page check failed", exc_info=True)


def _backend_unavailable_response(
    resolved: ResolvedFailoverChannel,
) -> Response:
    response = jsonify(
        {
            "status": "error",
            "code": "backend_unavailable",
            "message": (
                "No healthy household API backend is currently available."
            ),
            "route_channel": resolved.channel,
            "primary_backend": "modal",
            "fallback_backend": "cloud_run",
            "retry_after_seconds": RETRY_AFTER_SECONDS,
        }
    )
    response.status_code = 503
    response.headers["Retry-After"] = str(RETRY_AFTER_SECONDS)
    return response


def _with_gateway_headers(
    response: Response,
    *,
    backend: str,
    primary_state: str,
    channel: str,
) -> Response:
    response.headers["X-PolicyEngine-Backend"] = backend
    response.headers["X-PolicyEngine-Primary-Backend"] = "modal"
    response.headers["X-PolicyEngine-Primary-State"] = primary_state
    response.headers["X-PolicyEngine-Route-Channel"] = channel
    return response


def _cloud_run_auth_header(audience: str) -> dict[str, str]:
    if os.getenv("HOUSEHOLD_FAILOVER_DISABLE_CLOUD_RUN_AUTH"):
        return {}
    token = id_token.fetch_id_token(GoogleAuthRequest(), audience)
    return {"Authorization": f"Bearer {token}"}


def _join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"
