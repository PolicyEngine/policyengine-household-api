from __future__ import annotations

import concurrent.futures
from contextvars import copy_context
from dataclasses import dataclass
import json
import logging
import os
import threading
import time
from typing import Any, Callable
from urllib import error, request as urllib_request

from flask import Flask, Response, jsonify, request
from google.auth import exceptions as google_auth_exceptions
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import id_token

from policyengine_household_common.constants import COUNTRIES
from policyengine_household_common.dispatch_codec import (
    decode_dispatch_response,
    encode_dispatch_request,
)
from policyengine_household_failover.manifest import (
    FAILOVER_MANIFEST_BLOB_ENV,
    FAILOVER_MANIFEST_BUCKET_ENV,
    FailoverManifestError,
    FailoverManifestReadError,
    FailoverManifestUnavailable,
    FailoverRoutingError,
    ResolvedFailoverChannel,
    public_versions_view,
    resolve_failover_channel_for_request,
    validate_failover_manifest,
)
from policyengine_household_common.request_limits import (
    max_content_length_bytes,
)
from policyengine_household_common.observability.flask import (
    init_observability,
)
from policyengine_household_common.observability.segments import SegmentName
from policyengine_observability import record_error
from policyengine_observability import record_event
from policyengine_observability import segment
from policyengine_observability import set_attribute
from policyengine_household_common.gateway import (
    VERSIONED_ENDPOINTS,
    _country_and_endpoint,
    _extract_requested_version,
    _json_error,
    _request_payload,
    _response_from_dispatch_result,
)
from policyengine_household_common.version_routing import VersionRoutingError


LOGGER = logging.getLogger(__name__)
MODAL_STATUS_URL = "https://status.modal.com/index.json"
FORCE_BACKEND_ENV = "HOUSEHOLD_FAILOVER_FORCE_BACKEND"
MODAL_ENVIRONMENT_ENV = "MODAL_ENVIRONMENT"
MODAL_CANARY_APP_NAME_ENV = "HOUSEHOLD_MODAL_CANARY_APP_NAME"
MODAL_CANARY_FUNCTION_NAME_ENV = (
    "HOUSEHOLD_FAILOVER_MODAL_CANARY_FUNCTION_NAME"
)
RETRY_AFTER_SECONDS = 10
MODAL_CANARY_APP_NAME = "policyengine-household-api-canary"
MODAL_CANARY_FUNCTION_NAME = "ping"
MODAL_FAILURE_MIN_COUNT = 10
MODAL_FAILURE_RATE = 0.5
MODAL_FAILURE_WINDOW_SECONDS = 60.0
MODAL_PROBE_INTERVAL_SECONDS = 15
MODAL_STATUS_CHECK_MIN_INTERVAL_SECONDS = 60
MODAL_MIN_OPEN_SECONDS = 60.0
MODAL_RECOVERY_SUCCESSES = 3
MANIFEST_CACHE_SECONDS = 30
# Long enough to absorb a cold Modal worker's first response (container boot +
# country model load), which can take tens of seconds, without converting a
# slow-but-healthy calculation into a 503. Probe/canary timeouts stay short.
MODAL_REQUEST_TIMEOUT_SECONDS = 90.0
MODAL_PROBE_TIMEOUT_SECONDS = 5.0
MODAL_CANARY_TIMEOUT_SECONDS = 5.0
CLOUD_RUN_WORKER_TIMEOUT_SECONDS = 180.0
MODAL_EXECUTOR_MAX_WORKERS = 32
MODAL_PROBE_EXECUTOR_MAX_WORKERS = 8

# Real user requests to Modal run on this executor. Saturating it is a local
# capacity limit, not a Modal outage.
_MODAL_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=MODAL_EXECUTOR_MAX_WORKERS,
    thread_name_prefix="household-modal",
)
_MODAL_EXECUTOR_SEMAPHORE = threading.BoundedSemaphore(
    MODAL_EXECUTOR_MAX_WORKERS,
)

# Health probes and the canary confirmation run on a dedicated executor so they
# stay independent of request-path saturation: request load can never both
# supply Modal failure evidence and "confirm" it through the same starved
# pool, and a hung request call can never starve the probes that recover the
# circuit.
_MODAL_PROBE_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=MODAL_PROBE_EXECUTOR_MAX_WORKERS,
    thread_name_prefix="household-modal-probe",
)
_MODAL_PROBE_EXECUTOR_SEMAPHORE = threading.BoundedSemaphore(
    MODAL_PROBE_EXECUTOR_MAX_WORKERS,
)


class ModalBackendUnavailable(RuntimeError):
    pass


class ModalExecutorSaturated(ModalBackendUnavailable):
    """The gateway's own executor was full, so no Modal call was attempted."""

    pass


class FallbackBackendUnavailable(RuntimeError):
    pass


@dataclass
class ChannelCircuit:
    attempts: list[tuple[float, bool]] | None = None
    is_open: bool = False
    opened_at: float = 0.0
    last_probe_at: float = 0.0
    last_modal_status_check_at: float = 0.0
    recovery_successes: int = 0

    def __post_init__(self) -> None:
        if self.attempts is None:
            self.attempts = []


@dataclass(frozen=True)
class ModalCircuitPolicy:
    failure_min_count: int = MODAL_FAILURE_MIN_COUNT
    failure_rate: float = MODAL_FAILURE_RATE
    failure_window_seconds: float = MODAL_FAILURE_WINDOW_SECONDS
    min_open_seconds: float = MODAL_MIN_OPEN_SECONDS
    recovery_successes: int = MODAL_RECOVERY_SUCCESSES


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

    def is_open(self, channel: str) -> bool:
        return self.state(channel).is_open

    def should_probe(self, channel: str) -> bool:
        circuit = self.state(channel)
        return (
            self._time() - circuit.last_probe_at
            >= MODAL_PROBE_INTERVAL_SECONDS
        )

    def record_probe_attempt(self, channel: str) -> None:
        with self._lock:
            self._circuits[channel].last_probe_at = self._time()

    def record_success(
        self,
        channel: str,
        policy: ModalCircuitPolicy,
    ) -> None:
        with self._lock:
            circuit = self._circuits[channel]
            now = self._time()
            circuit.attempts.append((now, True))
            self._trim_attempts(circuit, now, policy.failure_window_seconds)
            circuit.recovery_successes = 0

    def record_failure(
        self,
        channel: str,
        policy: ModalCircuitPolicy,
    ) -> bool:
        with self._lock:
            circuit = self._circuits[channel]
            now = self._time()
            circuit.attempts.append((now, False))
            circuit.recovery_successes = 0
            self._trim_attempts(circuit, now, policy.failure_window_seconds)
            if circuit.is_open:
                return False
            return self._threshold_reached(circuit, policy)

    def open(self, channel: str) -> None:
        with self._lock:
            circuit = self._circuits[channel]
            circuit.is_open = True
            circuit.opened_at = self._time()
            circuit.recovery_successes = 0

    def ready_for_recovery_probe(
        self,
        channel: str,
        policy: ModalCircuitPolicy,
    ) -> bool:
        with self._lock:
            circuit = self._circuits[channel]
            return (
                circuit.is_open
                and self._time() - circuit.opened_at >= policy.min_open_seconds
            )

    def record_recovery_success(
        self,
        channel: str,
        policy: ModalCircuitPolicy,
    ) -> bool:
        with self._lock:
            circuit = self._circuits[channel]
            circuit.recovery_successes += 1
            if circuit.recovery_successes < policy.recovery_successes:
                return False
            circuit.is_open = False
            circuit.opened_at = 0.0
            circuit.recovery_successes = 0
            circuit.attempts.clear()
            circuit.attempts.append((self._time(), True))
            return True

    def record_recovery_failure(self, channel: str) -> None:
        with self._lock:
            self._circuits[channel].recovery_successes = 0

    def should_check_modal_status(self, channel: str) -> bool:
        with self._lock:
            circuit = self._circuits[channel]
            return (
                self._time() - circuit.last_modal_status_check_at
                >= MODAL_STATUS_CHECK_MIN_INTERVAL_SECONDS
            )

    def record_modal_status_check(self, channel: str) -> None:
        with self._lock:
            self._circuits[channel].last_modal_status_check_at = self._time()

    def _threshold_reached(
        self,
        circuit: ChannelCircuit,
        policy: ModalCircuitPolicy,
    ) -> bool:
        attempts = circuit.attempts or []
        failures = sum(1 for _, succeeded in attempts if not succeeded)
        if failures < policy.failure_min_count:
            return False
        return failures / len(attempts) >= policy.failure_rate

    def _trim_attempts(
        self,
        circuit: ChannelCircuit,
        now: float,
        window_seconds: float,
    ) -> None:
        cutoff = now - window_seconds
        circuit.attempts[:] = [
            attempt
            for attempt in circuit.attempts or []
            if attempt[0] >= cutoff
        ]


class GcsFailoverManifestLoader:
    def __init__(
        self,
        *,
        bucket_name: str | None = None,
        blob_name: str | None = None,
        cache_seconds: int = MANIFEST_CACHE_SECONDS,
        time_source: Callable[[], float] | None = None,
        fetch: Callable[[], Any] | None = None,
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
        self._fetch = fetch
        self._cached_manifest: dict[str, Any] | None = None
        self._cached_at = 0.0

    def __call__(self) -> dict[str, Any]:
        now = self._time()
        if self._cached_manifest and (
            now - self._cached_at < self.cache_seconds
        ):
            return self._cached_manifest
        try:
            manifest = validate_failover_manifest(self._download_manifest())
            self._cached_manifest = manifest
            self._cached_at = now
            return manifest
        except Exception as exc:
            if self._cached_manifest is not None:
                # A transient GCS/read error shouldn't turn into request-wide
                # 503s. Serve the last-known-good manifest and revalidate it on
                # the next cache window rather than hammering GCS per request.
                self._cached_at = now
                LOGGER.warning(
                    "Failed to refresh Cloud Run failover manifest; serving "
                    "last-known-good manifest",
                    exc_info=True,
                )
                return self._cached_manifest
            raise FailoverManifestReadError(
                "Could not read Cloud Run failover manifest"
            ) from exc

    def _download_manifest(self) -> Any:
        if self._fetch is not None:
            return self._fetch()
        if not self.bucket_name:
            raise ValueError(f"{FAILOVER_MANIFEST_BUCKET_ENV} must be set")

        from google.cloud import storage

        client = storage.Client()
        blob = client.bucket(self.bucket_name).blob(self.blob_name)
        return json.loads(blob.download_as_text())


def create_gateway_app(
    *,
    manifest_loader: Callable[[], dict[str, Any]] | None = None,
    modal_request: Callable[[str, dict[str, Any]], Response] | None = None,
    modal_health_probe: Callable[[str], None] | None = None,
    modal_canary_probe: Callable[[], None] | None = None,
    fallback_request: (
        Callable[[ResolvedFailoverChannel, dict[str, Any]], Response] | None
    ) = None,
    modal_status_checker: Callable[[], dict[str, Any]] | None = None,
    fallback_warmup: Callable[[ResolvedFailoverChannel], None] | None = None,
    circuit_registry: CircuitRegistry | None = None,
    circuit_policy: ModalCircuitPolicy | None = None,
    modal_timeout_seconds: float | None = None,
    modal_request_timeout_seconds: float | None = None,
    modal_probe_timeout_seconds: float | None = None,
    modal_canary_timeout_seconds: float | None = None,
) -> Flask:
    app = Flask(__name__)
    init_observability(app, service_role="failover_gateway")
    # Reject oversized request bodies before buffering them via
    # ``request.get_data()`` on a small gateway container.
    app.config["MAX_CONTENT_LENGTH"] = max_content_length_bytes()
    load_manifest = manifest_loader or GcsFailoverManifestLoader()
    call_modal = modal_request or call_modal_worker
    probe_modal = modal_health_probe or probe_modal_worker
    probe_canary = modal_canary_probe or probe_modal_canary
    call_fallback = fallback_request or call_cloud_run_worker
    check_modal_status = modal_status_checker or fetch_modal_status
    warm_fallback = fallback_warmup or warm_cloud_run_worker
    circuits = circuit_registry or CircuitRegistry()
    policy = circuit_policy or modal_circuit_policy_from_env()
    request_timeout = (
        max(modal_request_timeout_seconds, 0.001)
        if modal_request_timeout_seconds is not None
        else _modal_operation_timeout_seconds(
            "HOUSEHOLD_FAILOVER_MODAL_REQUEST_TIMEOUT_SECONDS",
            MODAL_REQUEST_TIMEOUT_SECONDS,
            legacy_timeout_seconds=modal_timeout_seconds,
        )
    )
    canary_timeout = (
        max(modal_canary_timeout_seconds, 0.001)
        if modal_canary_timeout_seconds is not None
        else _operation_timeout_seconds(
            "HOUSEHOLD_FAILOVER_MODAL_CANARY_TIMEOUT_SECONDS",
            MODAL_CANARY_TIMEOUT_SECONDS,
        )
    )
    probe_timeout = (
        max(modal_probe_timeout_seconds, 0.001)
        if modal_probe_timeout_seconds is not None
        else _modal_operation_timeout_seconds(
            "HOUSEHOLD_FAILOVER_MODAL_PROBE_TIMEOUT_SECONDS",
            MODAL_PROBE_TIMEOUT_SECONDS,
            legacy_timeout_seconds=modal_timeout_seconds,
        )
    )

    @app.get("/liveness_check")
    def liveness_check() -> Response:
        return Response("OK", status=200, mimetype="text/plain")

    @app.get("/readiness_check")
    def readiness_check() -> Response:
        try:
            manifest = validate_failover_manifest(load_manifest())
        except FailoverManifestError as exc:
            return _gateway_unavailable_response(str(exc))
        if not manifest["channels"].get("current"):
            return _gateway_unavailable_response(
                "No current failover channel is configured"
            )
        return Response("OK", status=200, mimetype="text/plain")

    @app.get("/versions")
    def versions() -> Response:
        try:
            return jsonify(public_versions_view(load_manifest()))
        except FailoverManifestError as exc:
            return _gateway_unavailable_response(str(exc))

    @app.get("/versions/<country_id>")
    def country_versions(country_id: str) -> Response:
        if country_id not in COUNTRIES:
            return _json_error(f"Unsupported country `{country_id}`", 404)

        try:
            manifest = validate_failover_manifest(load_manifest())
        except FailoverManifestError as exc:
            return _gateway_unavailable_response(str(exc))
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
        set_attribute("country_id", country_id)
        set_attribute("endpoint", endpoint)

        try:
            with segment(SegmentName.MANIFEST_LOAD):
                manifest = validate_failover_manifest(load_manifest())
        except FailoverManifestError as exc:
            record_error(exc, handled=True, status_code=503)
            return _gateway_unavailable_response(str(exc))

        try:
            with segment(SegmentName.VERSION_RESOLUTION):
                if country_id and endpoint in VERSIONED_ENDPOINTS:
                    body, requested_version = _extract_requested_version(body)
                else:
                    requested_version = "current"
                resolved = resolve_failover_channel_for_request(
                    manifest,
                    country_id=country_id,
                    requested_version=requested_version,
                )
            set_attribute("requested_version", resolved.requested_version)
            set_attribute("resolved_channel", resolved.channel)
            payload = _request_payload(path, body, resolved)
            response, backend = _route_to_backend(
                resolved,
                payload,
                circuits=circuits,
                policy=policy,
                call_modal=call_modal,
                probe_modal=probe_modal,
                probe_canary=probe_canary,
                call_fallback=call_fallback,
                check_modal_status=check_modal_status,
                warm_fallback=warm_fallback,
                modal_request_timeout_seconds=request_timeout,
                modal_probe_timeout_seconds=probe_timeout,
                modal_canary_timeout_seconds=canary_timeout,
            )
            set_attribute("backend", backend)
            return _with_gateway_headers(
                response,
                backend=backend,
                channel=resolved.channel,
                primary_state=circuits.primary_state(resolved.channel),
            )
        except FailoverManifestUnavailable as exc:
            record_error(exc, handled=True, status_code=503)
            return _gateway_unavailable_response(str(exc))
        except (FailoverRoutingError, VersionRoutingError) as exc:
            status_code = getattr(exc, "status_code", 400)
            record_error(
                exc,
                handled=True,
                status_code=status_code,
                include_stack=False,
            )
            return _json_error(
                str(exc),
                status_code,
                code=getattr(exc, "code", None),
                requested_version=getattr(exc, "requested_version", None),
                country_id=getattr(exc, "country_id", None),
                available_versions=getattr(exc, "available_versions", None),
            )

    return app


def call_modal_worker(app_name: str, payload: dict[str, Any]) -> Response:
    return _response_from_dispatch_result(
        _call_modal_worker_dispatch(app_name, payload)
    )


def probe_modal_worker(app_name: str) -> None:
    result = _call_modal_worker_dispatch(
        app_name,
        {
            "method": "GET",
            "path": "/liveness_check",
            "query_string": "",
            "headers": {},
            "body": b"",
        },
    )
    if int(result["status_code"]) != 200:
        raise ModalBackendUnavailable("Modal worker liveness check failed")


def probe_modal_canary() -> None:
    import modal

    app_name = os.getenv(MODAL_CANARY_APP_NAME_ENV, MODAL_CANARY_APP_NAME)
    function_name = os.getenv(
        MODAL_CANARY_FUNCTION_NAME_ENV,
        MODAL_CANARY_FUNCTION_NAME,
    )
    try:
        with segment(SegmentName.MODAL_WORKER_LOOKUP, backend="modal"):
            canary_function = _modal_lookup(
                modal.Function.from_name,
                app_name,
                function_name,
            )
        with segment(SegmentName.MODAL_REMOTE_EXECUTION, backend="modal"):
            result = canary_function.remote()
    except Exception as exc:
        raise ModalBackendUnavailable(str(exc)) from exc
    if not isinstance(result, dict) or result.get("ok") is not True:
        raise ModalBackendUnavailable("Modal canary returned unhealthy result")


def _call_modal_worker_dispatch(
    app_name: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    import modal

    try:
        with segment(SegmentName.MODAL_WORKER_LOOKUP, backend="modal"):
            worker_cls = _modal_lookup(
                modal.Cls.from_name,
                app_name,
                "HouseholdWorker",
            )
        with segment(SegmentName.MODAL_REMOTE_EXECUTION, backend="modal"):
            return worker_cls().handle_household_request.remote(payload)
    except modal.exception.NotFoundError:
        try:
            with segment(SegmentName.MODAL_WORKER_LOOKUP, backend="modal"):
                worker_function = _modal_lookup(
                    modal.Function.from_name,
                    app_name,
                    "handle_household_request",
                )
            with segment(SegmentName.MODAL_REMOTE_EXECUTION, backend="modal"):
                return worker_function.remote(payload)
        except Exception as exc:
            raise ModalBackendUnavailable(str(exc)) from exc
    except Exception as exc:
        raise ModalBackendUnavailable(str(exc)) from exc


def call_cloud_run_worker(
    resolved: ResolvedFailoverChannel,
    payload: dict[str, Any],
) -> Response:
    dispatch_url = _join_url(
        resolved.cloud_run_worker_url,
        "/_internal/dispatch",
    )
    body = json.dumps(encode_dispatch_request(payload)).encode("utf-8")
    try:
        with segment(SegmentName.CLOUD_RUN_AUTH, backend="cloud_run"):
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
        with segment(SegmentName.CLOUD_RUN_HTTP_REQUEST, backend="cloud_run"):
            with urllib_request.urlopen(
                req,
                timeout=_operation_timeout_seconds(
                    "HOUSEHOLD_FAILOVER_CLOUD_RUN_WORKER_TIMEOUT_SECONDS",
                    CLOUD_RUN_WORKER_TIMEOUT_SECONDS,
                ),
            ) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        with segment(
            SegmentName.CLOUD_RUN_RESPONSE_DECODE, backend="cloud_run"
        ):
            dispatch_result = decode_dispatch_response(response_payload)
    except (
        OSError,
        error.HTTPError,
        error.URLError,
        google_auth_exceptions.GoogleAuthError,
        json.JSONDecodeError,
        UnicodeDecodeError,
        ValueError,
    ) as exc:
        raise FallbackBackendUnavailable(str(exc)) from exc
    return _response_from_dispatch_result(dispatch_result)


def warm_cloud_run_worker(resolved: ResolvedFailoverChannel) -> None:
    health_url = _join_url(resolved.cloud_run_worker_url, "/liveness_check")
    try:
        with segment(SegmentName.FALLBACK_WARMUP, backend="cloud_run"):
            headers = _cloud_run_auth_header(resolved.cloud_run_worker_url)
            req = urllib_request.Request(
                health_url,
                headers=headers,
                method="GET",
            )
            urllib_request.urlopen(req, timeout=5).close()
    except (
        OSError,
        error.HTTPError,
        error.URLError,
        google_auth_exceptions.GoogleAuthError,
        ValueError,
    ):
        LOGGER.info("Cloud Run fallback warmup failed", exc_info=True)


def fetch_modal_status() -> dict[str, Any]:
    with segment(SegmentName.MODAL_STATUS_CHECK, backend="modal"):
        with urllib_request.urlopen(MODAL_STATUS_URL, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))


def _route_to_backend(
    resolved: ResolvedFailoverChannel,
    payload: dict[str, Any],
    *,
    circuits: CircuitRegistry,
    policy: ModalCircuitPolicy,
    call_modal: Callable[[str, dict[str, Any]], Response],
    probe_modal: Callable[[str], None],
    probe_canary: Callable[[], None],
    call_fallback: Callable[
        [ResolvedFailoverChannel, dict[str, Any]], Response
    ],
    check_modal_status: Callable[[], dict[str, Any]],
    warm_fallback: Callable[[ResolvedFailoverChannel], None],
    modal_request_timeout_seconds: float,
    modal_probe_timeout_seconds: float,
    modal_canary_timeout_seconds: float,
) -> tuple[Response, str]:
    force_backend = os.getenv(FORCE_BACKEND_ENV, "").strip().lower()
    if force_backend == "cloud_run":
        record_event("fallback_selected", reason="forced_cloud_run")
        return _route_to_fallback_or_503(
            resolved,
            payload,
            call_fallback=call_fallback,
        )

    if force_backend != "modal":
        with segment(SegmentName.CIRCUIT_REFRESH, backend="modal"):
            _refresh_modal_circuit(
                resolved,
                circuits=circuits,
                policy=policy,
                probe_modal=probe_modal,
                probe_canary=probe_canary,
                check_modal_status=check_modal_status,
                warm_fallback=warm_fallback,
                modal_probe_timeout_seconds=modal_probe_timeout_seconds,
                modal_canary_timeout_seconds=modal_canary_timeout_seconds,
            )
        if circuits.is_open(resolved.channel):
            record_event(
                "fallback_selected",
                reason="modal_circuit_open",
                channel=resolved.channel,
            )
            return _route_to_fallback_or_503(
                resolved,
                payload,
                call_fallback=call_fallback,
            )

    try:
        with segment(SegmentName.MODAL_REQUEST, backend="modal"):
            response = _run_modal_operation(
                lambda: call_modal(resolved.modal_app_name, payload),
                timeout_seconds=modal_request_timeout_seconds,
            )
        circuits.record_success(resolved.channel, policy)
        return response, "modal"
    except ModalExecutorSaturated:
        # The gateway's own request executor is full. That is a local capacity
        # limit, not a Modal outage, so shed load with a 503 without recording
        # circuit-breaker failure evidence or triggering a fallback.
        record_event(
            "modal_executor_saturated",
            channel=resolved.channel,
            backend="none",
        )
        return _backend_unavailable_response(resolved), "none"
    except ModalBackendUnavailable:
        record_event(
            "modal_request_failed",
            channel=resolved.channel,
            backend="modal",
        )
        if force_backend == "modal":
            return _backend_unavailable_response(resolved), "none"
        if circuits.record_failure(resolved.channel, policy):
            _log_modal_status_after_threshold(
                resolved.channel,
                circuits=circuits,
                check_modal_status=check_modal_status,
            )
            if _modal_canary_confirms_outage(
                probe_canary=probe_canary,
                timeout_seconds=modal_canary_timeout_seconds,
            ):
                circuits.open(resolved.channel)
                record_event(
                    "modal_circuit_opened",
                    channel=resolved.channel,
                )
                warm_fallback(resolved)
                record_event(
                    "fallback_selected",
                    reason="modal_canary_confirmed",
                    channel=resolved.channel,
                )
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
    policy: ModalCircuitPolicy,
    probe_modal: Callable[[str], None],
    probe_canary: Callable[[], None],
    check_modal_status: Callable[[], dict[str, Any]],
    warm_fallback: Callable[[ResolvedFailoverChannel], None],
    modal_probe_timeout_seconds: float,
    modal_canary_timeout_seconds: float,
) -> None:
    if circuits.is_open(resolved.channel):
        _refresh_open_modal_circuit(
            resolved,
            circuits=circuits,
            policy=policy,
            probe_modal=probe_modal,
            probe_canary=probe_canary,
            modal_probe_timeout_seconds=modal_probe_timeout_seconds,
            modal_canary_timeout_seconds=modal_canary_timeout_seconds,
        )
        return

    if not circuits.should_probe(resolved.channel):
        return
    circuits.record_probe_attempt(resolved.channel)
    try:
        with segment(SegmentName.MODAL_PROBE, backend="modal"):
            _run_modal_probe(
                lambda: probe_modal(resolved.modal_app_name),
                timeout_seconds=modal_probe_timeout_seconds,
            )
        circuits.record_success(resolved.channel, policy)
    except ModalExecutorSaturated:
        # Could not run an independent probe; skip it without recording a
        # Modal failure on the circuit.
        return
    except ModalBackendUnavailable:
        if circuits.record_failure(resolved.channel, policy):
            _log_modal_status_after_threshold(
                resolved.channel,
                circuits=circuits,
                check_modal_status=check_modal_status,
            )
            if _modal_canary_confirms_outage(
                probe_canary=probe_canary,
                timeout_seconds=modal_canary_timeout_seconds,
            ):
                circuits.open(resolved.channel)
                record_event(
                    "modal_circuit_opened",
                    channel=resolved.channel,
                    source="probe",
                )
                warm_fallback(resolved)


def _refresh_open_modal_circuit(
    resolved: ResolvedFailoverChannel,
    *,
    circuits: CircuitRegistry,
    policy: ModalCircuitPolicy,
    probe_modal: Callable[[str], None],
    probe_canary: Callable[[], None],
    modal_probe_timeout_seconds: float,
    modal_canary_timeout_seconds: float,
) -> None:
    if not circuits.ready_for_recovery_probe(resolved.channel, policy):
        return
    if not circuits.should_probe(resolved.channel):
        return
    circuits.record_probe_attempt(resolved.channel)
    try:
        with segment(SegmentName.MODAL_CANARY, backend="modal"):
            _run_modal_probe(
                probe_canary,
                timeout_seconds=modal_canary_timeout_seconds,
            )
        with segment(SegmentName.MODAL_PROBE, backend="modal"):
            _run_modal_probe(
                lambda: probe_modal(resolved.modal_app_name),
                timeout_seconds=modal_probe_timeout_seconds,
            )
        recovered = circuits.record_recovery_success(resolved.channel, policy)
        if recovered:
            record_event(
                "modal_circuit_recovered",
                channel=resolved.channel,
            )
    except ModalExecutorSaturated:
        # Local saturation is not Modal evidence; skip this recovery round
        # without resetting the in-progress recovery streak.
        return
    except ModalBackendUnavailable:
        circuits.record_recovery_failure(resolved.channel)


def _route_to_fallback_or_503(
    resolved: ResolvedFailoverChannel,
    payload: dict[str, Any],
    *,
    call_fallback: Callable[
        [ResolvedFailoverChannel, dict[str, Any]], Response
    ],
) -> tuple[Response, str]:
    try:
        with segment(SegmentName.CLOUD_RUN_REQUEST, backend="cloud_run"):
            return call_fallback(resolved, payload), "cloud_run"
    except FallbackBackendUnavailable:
        record_event(
            "backend_unavailable",
            backend="cloud_run",
            channel=resolved.channel,
        )
        return _backend_unavailable_response(resolved), "none"


def _modal_canary_confirms_outage(
    *,
    probe_canary: Callable[[], None],
    timeout_seconds: float,
) -> bool:
    try:
        with segment(SegmentName.MODAL_CANARY, backend="modal"):
            _run_modal_probe(
                probe_canary,
                timeout_seconds=timeout_seconds,
            )
        return False
    except ModalExecutorSaturated:
        # We could not run an independent canary check, so we cannot confirm a
        # Modal outage. Keep Modal as primary rather than opening the circuit
        # on local-saturation evidence alone.
        LOGGER.warning(
            "Modal canary executor saturated; cannot confirm Modal outage"
        )
        return False
    except ModalBackendUnavailable:
        return True


def _log_modal_status_after_threshold(
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
            "Modal failover threshold reached; status page snapshot: %s",
            modal_status_summary(check_modal_status()),
        )
    except Exception:
        LOGGER.warning("Modal status page check failed", exc_info=True)


def modal_status_summary(status: dict[str, Any]) -> dict[str, Any]:
    attributes = status.get("data", {}).get("attributes", {})
    summary: dict[str, Any] = {
        "aggregate_state": attributes.get("aggregate_state"),
        "resources": {},
    }
    relevant_names = {"CPU functions", "Web endpoints"}
    for included in status.get("included", []):
        if included.get("type") != "status_page_resource":
            continue
        resource = included.get("attributes", {})
        name = resource.get("public_name")
        if name not in relevant_names:
            continue
        summary["resources"][name] = resource.get("status")
    return summary


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


def _gateway_unavailable_response(message: str) -> Response:
    response = jsonify(
        {
            "status": "error",
            "code": "gateway_unavailable",
            "message": message,
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


def _run_modal_operation(
    operation: Callable[[], Any],
    *,
    timeout_seconds: float,
    executor: concurrent.futures.ThreadPoolExecutor = _MODAL_EXECUTOR,
    semaphore: threading.BoundedSemaphore = _MODAL_EXECUTOR_SEMAPHORE,
) -> Any:
    if not semaphore.acquire(blocking=False):
        raise ModalExecutorSaturated("Modal operation executor is saturated")

    try:
        context = copy_context()
        future = executor.submit(context.run, operation)
    except Exception:
        semaphore.release()
        raise

    future.add_done_callback(lambda _: semaphore.release())
    try:
        return future.result(timeout=timeout_seconds)
    except concurrent.futures.TimeoutError as exc:
        future.cancel()
        raise ModalBackendUnavailable(
            f"Modal operation timed out after {timeout_seconds:g}s"
        ) from exc
    except ModalBackendUnavailable:
        raise
    except Exception as exc:
        raise ModalBackendUnavailable(str(exc)) from exc


def _run_modal_probe(
    operation: Callable[[], Any],
    *,
    timeout_seconds: float,
) -> Any:
    """Run a health probe / canary check on the dedicated probe executor."""
    return _run_modal_operation(
        operation,
        timeout_seconds=timeout_seconds,
        executor=_MODAL_PROBE_EXECUTOR,
        semaphore=_MODAL_PROBE_EXECUTOR_SEMAPHORE,
    )


def _modal_operation_timeout_seconds(
    env_var: str,
    default: float,
    *,
    legacy_timeout_seconds: float | None = None,
) -> float:
    if legacy_timeout_seconds is not None:
        return max(legacy_timeout_seconds, 0.001)
    raw_value = os.getenv(env_var, "") or os.getenv(
        "HOUSEHOLD_FAILOVER_MODAL_TIMEOUT_SECONDS",
        "",
    )
    return _operation_timeout_seconds_from_value(raw_value, default)


def modal_circuit_policy_from_env() -> ModalCircuitPolicy:
    return ModalCircuitPolicy(
        failure_min_count=_operation_int_from_env(
            "HOUSEHOLD_FAILOVER_MODAL_FAILURE_MIN_COUNT",
            MODAL_FAILURE_MIN_COUNT,
            minimum=1,
        ),
        failure_rate=min(
            1.0,
            _operation_timeout_seconds(
                "HOUSEHOLD_FAILOVER_MODAL_FAILURE_RATE",
                MODAL_FAILURE_RATE,
            ),
        ),
        failure_window_seconds=_operation_timeout_seconds(
            "HOUSEHOLD_FAILOVER_MODAL_FAILURE_WINDOW_SECONDS",
            MODAL_FAILURE_WINDOW_SECONDS,
        ),
        min_open_seconds=_operation_timeout_seconds(
            "HOUSEHOLD_FAILOVER_MODAL_MIN_OPEN_SECONDS",
            MODAL_MIN_OPEN_SECONDS,
        ),
        recovery_successes=_operation_int_from_env(
            "HOUSEHOLD_FAILOVER_MODAL_RECOVERY_SUCCESSES",
            MODAL_RECOVERY_SUCCESSES,
            minimum=1,
        ),
    )


def _operation_int_from_env(
    env_var: str,
    default: int,
    *,
    minimum: int,
) -> int:
    raw_value = os.getenv(env_var, "")
    if not raw_value:
        return default
    try:
        value = int(raw_value)
    except ValueError:
        return default
    return max(value, minimum)


def _operation_timeout_seconds(env_var: str, default: float) -> float:
    return _operation_timeout_seconds_from_value(
        os.getenv(env_var, ""),
        default,
    )


def _operation_timeout_seconds_from_value(
    raw_value: str,
    default: float,
) -> float:
    if not raw_value:
        return default
    try:
        timeout = float(raw_value)
    except ValueError:
        return default
    return max(timeout, 0.001)


def _modal_lookup(
    lookup: Callable[..., Any],
    app_name: str,
    object_name: str,
) -> Any:
    environment = os.getenv(MODAL_ENVIRONMENT_ENV, "").strip()
    if environment:
        return lookup(
            app_name,
            object_name,
            environment_name=environment,
        )
    return lookup(app_name, object_name)


def _join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"
