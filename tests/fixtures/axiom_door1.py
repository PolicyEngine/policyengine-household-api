"""A fake ``policyengine_axiom`` for Door 1 unit tests.

The real package needs the Axiom rules engine's native extension and a
RuleSpec corpus root, neither of which the unit-test environment has. The
fake records what the host asks of it, in order.
"""

from __future__ import annotations

import contextlib
import enum
import sys
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from policyengine_household_api import axiom_door1


class FakeMode(enum.Enum):
    OFF = "off"
    SHADOW = "shadow"
    COMPARE = "compare"
    ON = "on"
    STRICT = "strict"


@dataclass
class FakeAggregates:
    sink: Path | None = None
    flushes: int = 0
    fail: bool = False

    def flush(self):
        if self.fail:
            raise OSError("volume unavailable")
        self.flushes += 1


@dataclass
class FakeLog:
    bound: list[str]
    aggregates: FakeAggregates = field(default_factory=FakeAggregates)


@dataclass
class FakeAxiom:
    """What the host did to the provider, in order."""

    calls: list[tuple] = field(default_factory=list)
    bound: tuple[str, ...] = ("snap",)
    apply_error: Exception | None = None
    request_error: Exception | None = None
    logs: list[FakeLog] = field(default_factory=list)
    default_mode: str | None = None
    # The cap the provider applies inside each request context, with
    # policyengine-axiom's rule: the context's own mode, else the process
    # default (``runtime.current_request_mode``).
    effective_caps: list[str | None] = field(default_factory=list)


def build_fake_runtime(axiom: FakeAxiom, *, request_cap: bool = True):
    runtime = types.ModuleType("policyengine_axiom.runtime")

    if request_cap:

        @contextlib.contextmanager
        def request_context(client_id, mode=None):
            if axiom.request_error is not None:
                raise axiom.request_error
            axiom.calls.append(("enter", client_id, mode))
            axiom.effective_caps.append(mode or axiom.default_mode)
            try:
                yield
            finally:
                axiom.calls.append(("exit", client_id, mode))

        def set_default_request_mode(mode):
            axiom.default_mode = mode
            axiom.calls.append(("default", mode))

        runtime.set_default_request_mode = set_default_request_mode
    else:
        # An older policyengine-axiom: labels the client, caps nothing.
        @contextlib.contextmanager
        def request_context(client_id):
            axiom.calls.append(("enter", client_id))
            yield

    runtime.request_context = request_context
    return runtime


def install_fake_policyengine_axiom(
    monkeypatch, *, request_cap: bool = True, **options: Any
) -> FakeAxiom:
    axiom = FakeAxiom(**options)
    package = types.ModuleType("policyengine_axiom")
    runtime = build_fake_runtime(axiom, request_cap=request_cap)
    package.runtime = runtime
    package.Mode = FakeMode

    def all_manifests(source=None):
        axiom.calls.append(("manifests", source))
        return ["manifest"]

    def apply_provider(system, manifests, mode=None, corpus_root=None):
        axiom.calls.append(("apply", system, tuple(manifests), mode))
        if axiom.apply_error is not None:
            raise axiom.apply_error
        log = FakeLog(bound=list(axiom.bound))
        axiom.logs.append(log)
        return log

    package.all_manifests = all_manifests
    package.apply_provider = apply_provider
    monkeypatch.setitem(sys.modules, "policyengine_axiom", package)
    monkeypatch.setitem(sys.modules, "policyengine_axiom.runtime", runtime)
    return axiom


def fake_countries():
    return {
        "us": types.SimpleNamespace(tax_benefit_system="us-system"),
        "uk": types.SimpleNamespace(tax_benefit_system="uk-system"),
    }


def enabled_settings(**overrides: Any) -> axiom_door1.Door1Settings:
    values = {"enabled": True, "mode": "compare"}
    values.update(overrides)
    return axiom_door1.Door1Settings(**values)


@pytest.fixture
def door1_reset():
    axiom_door1.reset_door1_for_tests()
    yield
    axiom_door1.reset_door1_for_tests()
