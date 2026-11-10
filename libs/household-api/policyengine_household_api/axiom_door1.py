"""Door 1: Axiom rules under the household API, through policyengine-axiom.

Off by default. Nothing here imports ``policyengine_axiom`` unless
``axiom_door1.enabled`` is true, and every public function here returns
instead of raising: a Door 1 problem must never change what a customer
receives, beyond the provider answering a variable that PolicyEngine would
otherwise answer.

Three integration points, all called by the host:

1. ``bind_door1()``: once per worker process, after the country systems are
   built and before their parameter caches are prewarmed (the Modal worker's
   memory-snapshot hook). It binds the shipped Axiom manifests into the
   shared country system in place, so there is still one system per country.
2. ``calculation_scope(country_id)``: around every ``country.calculate`` call.
   It puts the request (resolved channel, client) in one of three tiers and
   tells the provider, per request, how far Axiom may go:

   - ``selected``: the serving tier (``serve_channels``, and ``clients`` when
     that list is not empty). The provider is capped to the bind-time mode,
     so the bind-time mode applies.
   - ``shadow``: any other request on a ``shadow_channels`` channel. The
     provider is capped to ``shadow``: PolicyEngine answers and Axiom is only
     compared. ``shadow_channels`` is empty by default.
   - ``unselected``: everything else. The provider is capped to ``off``:
     PolicyEngine's formula answers and no Axiom code runs.

   A cap only lowers a binding, never raises it. A calculation outside any
   scope is capped to ``off`` too (the process default set before binding), so
   the guarantee does not depend on every call site remembering the scope.
3. ``configure_door1_runtime(...)`` and ``flush_door1()``: after a memory
   snapshot restore (per-container sink directory) and at container exit (the
   last window of outcome counts).

The per-request cap needs two functions from ``policyengine_axiom.runtime``:
``request_context(client_id, mode=...)`` and ``set_default_request_mode(mode)``.
Without them this module does not bind.
"""

from __future__ import annotations

import contextlib
import inspect
import logging
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

logger = logging.getLogger(__name__)

CONFIG_PREFIX = "axiom_door1"
# Modes a serving host may bind with. ``strict`` re-raises engine errors into
# the customer's calculation and ``off`` binds nothing; neither belongs here.
SERVING_MODES = ("shadow", "compare", "on")
DEFAULT_MODE = "shadow"
DEFAULT_SERVE_CHANNELS = ("frontier",)
DEFAULT_COUNTRIES = ("us",)
# What a request that is not selected gets: the provider runs no Axiom code
# and PolicyEngine's own formula answers.
UNSELECTED_MODE = "off"
# What a request in the shadow tier gets: PolicyEngine answers, Axiom is
# computed and compared.
SHADOW_MODE = "shadow"
MANIFEST_SOURCE = "files"

# Request tiers. The value is also the ``axiom_door1`` log attribute.
SERVE_TIER = "selected"
SHADOW_TIER = "shadow"
UNSELECTED_TIER = "unselected"


@dataclass(frozen=True)
class Door1Settings:
    enabled: bool = False
    mode: str = DEFAULT_MODE
    serve_channels: frozenset[str] = frozenset(DEFAULT_SERVE_CHANNELS)
    clients: frozenset[str] = frozenset()
    # Channels whose requests outside the serving tier still run Axiom in
    # shadow. Empty: they get PolicyEngine with the provider off.
    shadow_channels: frozenset[str] = frozenset()
    countries: frozenset[str] = frozenset(DEFAULT_COUNTRIES)
    corpus_root: str | None = None


@dataclass
class Door1State:
    """What ``bind_door1`` did in this process."""

    settings: Door1Settings = field(default_factory=Door1Settings)
    bound_countries: frozenset[str] = frozenset()
    reason: str = "not bound"
    runtime: Any = None
    logs: dict[str, Any] = field(default_factory=dict)

    @property
    def bound(self) -> bool:
        return bool(self.bound_countries) and self.runtime is not None


_state = Door1State()
_lock = threading.Lock()


def state() -> Door1State:
    return _state


def reset_door1_for_tests() -> None:
    global _state
    _state = Door1State()


# ---------------------------------------------------------------------------
# settings
# ---------------------------------------------------------------------------


def load_settings(
    get_value: Callable[[str, Any], Any] | None = None,
) -> Door1Settings:
    """Read ``axiom_door1.*`` (config file, or ``AXIOM_DOOR1__*`` env vars)."""
    if get_value is None:
        from policyengine_household_common.config_loader import (
            get_config_value,
        )

        get_value = get_config_value

    def value(key: str, default: Any) -> Any:
        return get_value(f"{CONFIG_PREFIX}.{key}", default)

    corpus_root = value("corpus_root", None)
    return Door1Settings(
        enabled=_as_bool(value("enabled", False)),
        mode=str(value("mode", DEFAULT_MODE) or DEFAULT_MODE).strip().lower(),
        serve_channels=_as_names(
            value("serve_channels", DEFAULT_SERVE_CHANNELS)
        ),
        clients=_as_names(value("clients", ())),
        shadow_channels=_as_names(value("shadow_channels", ())),
        countries=_as_names(value("countries", DEFAULT_COUNTRIES)),
        corpus_root=str(corpus_root) if corpus_root else None,
    )


def _as_bool(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _as_names(raw: Any) -> frozenset[str]:
    """A list, or a comma-separated string (the env-var form)."""
    if raw is None:
        return frozenset()
    if isinstance(raw, str):
        items = raw.split(",")
    elif isinstance(raw, (list, tuple, set, frozenset)):
        items = raw
    else:
        return frozenset()
    return frozenset(str(item).strip() for item in items if str(item).strip())


# ---------------------------------------------------------------------------
# 1. bind once per worker
# ---------------------------------------------------------------------------


def bind_door1(
    countries: Mapping[str, Any] | None = None,
    settings: Door1Settings | None = None,
) -> Door1State:
    """Bind Axiom's manifests into the country systems. Never raises.

    ``countries`` defaults to ``policyengine_household_api.country.COUNTRIES``;
    each value needs a ``tax_benefit_system``. Call it once, before the
    parameter caches are prewarmed.
    """
    global _state
    with _lock:
        if _state.bound:
            return _state
        try:
            _state = _bind(countries, settings)
        except Exception as exc:  # the host keeps answering with PE
            logger.exception("Door 1 bind failed; PolicyEngine answers")
            _state = Door1State(
                settings=settings or Door1Settings(),
                reason=f"bind failed: {type(exc).__name__}: {exc}",
            )
        logger.info("Door 1: %s", _state.reason)
        return _state


def _bind(
    countries: Mapping[str, Any] | None,
    settings: Door1Settings | None,
) -> Door1State:
    settings = settings or load_settings()
    if not settings.enabled:
        return Door1State(settings=settings, reason="disabled by config")
    if settings.mode not in SERVING_MODES:
        return Door1State(
            settings=settings,
            reason=(
                f"mode {settings.mode!r} is not one of {SERVING_MODES}; "
                "not bound"
            ),
        )

    try:
        import policyengine_axiom
        from policyengine_axiom import runtime as axiom_runtime
    except ImportError as exc:
        return Door1State(
            settings=settings,
            reason=f"policyengine-axiom is not installed: {exc}",
        )

    missing = _missing_request_cap(axiom_runtime)
    if missing:
        return Door1State(
            settings=settings,
            reason=(
                "policyengine-axiom has no request-level mode cap "
                f"(missing {missing}); not bound, so no request can "
                "receive an Axiom answer outside its channel"
            ),
        )

    # Fail closed: before anything is bound, a calculation outside an
    # explicit Door 1 scope gets PolicyEngine's formula.
    axiom_runtime.set_default_request_mode(UNSELECTED_MODE)

    if countries is None:
        from policyengine_household_api.country import COUNTRIES

        countries = COUNTRIES

    mode = policyengine_axiom.Mode(settings.mode)
    manifests = policyengine_axiom.all_manifests(source=MANIFEST_SOURCE)
    bound: set[str] = set()
    logs: dict[str, Any] = {}
    notes: list[str] = []
    for country_id in sorted(settings.countries):
        country = countries.get(country_id)
        if country is None:
            notes.append(f"{country_id}: no such country")
            continue
        log = policyengine_axiom.apply_provider(
            country.tax_benefit_system,
            manifests,
            mode=mode,
            corpus_root=settings.corpus_root,
        )
        logs[country_id] = log
        names = list(getattr(log, "bound", []) or [])
        if names:
            bound.add(country_id)
            notes.append(f"{country_id}: {len(names)} variable(s) bound")
        else:
            notes.append(f"{country_id}: nothing bound")

    return Door1State(
        settings=settings,
        bound_countries=frozenset(bound),
        reason="; ".join([f"mode {settings.mode}", _describe_tiers(settings)])
        + "; "
        + "; ".join(notes),
        runtime=axiom_runtime if bound else None,
        logs=logs,
    )


def _describe_tiers(settings: Door1Settings) -> str:
    serve = ",".join(sorted(settings.serve_channels)) or "none"
    if settings.clients:
        serve += f" ({len(settings.clients)} listed client(s))"
    shadow = ",".join(sorted(settings.shadow_channels)) or "none"
    return f"serve {serve}; shadow {shadow}"


def _missing_request_cap(axiom_runtime: Any) -> list[str]:
    missing = []
    if not callable(getattr(axiom_runtime, "set_default_request_mode", None)):
        missing.append("runtime.set_default_request_mode")
    request_context = getattr(axiom_runtime, "request_context", None)
    try:
        accepts_mode = "mode" in inspect.signature(request_context).parameters
    except (TypeError, ValueError):
        accepts_mode = False
    if not accepts_mode:
        missing.append("runtime.request_context(client_id, mode=...)")
    return missing


# ---------------------------------------------------------------------------
# 2. one scope per calculation
# ---------------------------------------------------------------------------


def request_tier(
    settings: Door1Settings,
    *,
    country_id: str | None,
    resolved_channel: str | None,
    client_id: str | None,
) -> str:
    """The tier of this request: ``selected``, ``shadow`` or ``unselected``.

    ``selected`` (the serving tier) wins over ``shadow``. A request reaches a
    worker with the channel the gateway resolved (``current`` or
    ``frontier``). A worker app keeps its memory snapshot when the weekly
    release promotes it from frontier to current, so the channel must be read
    per request, not per process.
    """
    if country_id not in settings.countries:
        return UNSELECTED_TIER
    if resolved_channel in settings.serve_channels and (
        not settings.clients or client_id in settings.clients
    ):
        return SERVE_TIER
    if resolved_channel in settings.shadow_channels:
        return SHADOW_TIER
    return UNSELECTED_TIER


def tier_cap(tier: str, settings: Door1Settings) -> str:
    """The request cap for a tier, as passed to ``request_context(mode=...)``.

    The serving tier passes the bind-time mode explicitly. It never lowers a
    binding, because no binding is above the bind-time mode. ``None`` would
    not work: in policyengine-axiom a context with ``mode=None`` falls back
    to the process default, which ``bind_door1`` sets to ``off``.
    """
    if tier == SERVE_TIER:
        return settings.mode
    if tier == SHADOW_TIER:
        return SHADOW_MODE
    return UNSELECTED_MODE


@contextlib.contextmanager
def calculation_scope(country_id: str) -> Iterator[None]:
    """Wrap one ``country.calculate`` call. A no-op unless Door 1 is bound."""
    current = _state
    if not current.bound or country_id not in current.bound_countries:
        yield
        return

    scope = contextlib.ExitStack()
    try:
        client_id = _client_id()
        tier = request_tier(
            current.settings,
            country_id=country_id,
            resolved_channel=_resolved_channel(),
            client_id=client_id,
        )
        scope.enter_context(
            current.runtime.request_context(
                client_id, mode=tier_cap(tier, current.settings)
            )
        )
        _set_observability_attribute("axiom_door1", tier)
    except Exception:
        # Entering failed: the process default (``off``) still applies, so
        # PolicyEngine answers this request.
        logger.warning(
            "Door 1 scope failed; PolicyEngine answers this request",
            exc_info=True,
        )
        scope.close()
        scope = contextlib.ExitStack()
    with scope:
        yield


def _resolved_channel() -> str | None:
    from flask import has_request_context, request
    from policyengine_household_common.routing_metadata import (
        RESOLVED_CHANNEL_ENVIRON_KEY,
    )

    if not has_request_context():
        return None
    channel = request.environ.get(RESOLVED_CHANNEL_ENVIRON_KEY)
    return channel if isinstance(channel, str) else None


def _client_id() -> str | None:
    from policyengine_household_api.decorators.analytics import (
        _client_id_from_request,
    )

    return _client_id_from_request()


def _set_observability_attribute(key: str, value: str) -> None:
    try:
        from policyengine_observability import set_attribute

        set_attribute(key, value)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 3. per-container runtime and exit
# ---------------------------------------------------------------------------


def configure_door1_runtime(
    *,
    sink_dir: str | Path | None,
    control_path: str | Path | None,
) -> None:
    """Point the provider at this container's sink and control file.

    Runs after a memory snapshot restore: containers restored from one
    snapshot share every object built before it, so the sink directory must
    be chosen here, per container, or their files would overwrite each other
    on a shared volume. Never raises.
    """
    current = _state
    if not current.bound:
        return
    try:
        if control_path is not None:
            os.environ["PE_AXIOM_CONTROL"] = str(control_path)
        for log in current.logs.values():
            aggregates = getattr(log, "aggregates", None)
            if aggregates is not None:
                aggregates.sink = Path(sink_dir) if sink_dir else None
    except Exception:
        logger.warning("Door 1 runtime configuration failed", exc_info=True)


def flush_door1() -> None:
    """Write the open window of outcome counts to the sink. Never raises."""
    for log in _state.logs.values():
        try:
            aggregates = getattr(log, "aggregates", None)
            if aggregates is not None:
                aggregates.flush()
        except Exception:
            logger.warning("Door 1 flush failed", exc_info=True)
