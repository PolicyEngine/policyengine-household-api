"""Door 1 host adapter: bind once, select per request, never raise."""

import os
import sys

import flask
import pytest

from policyengine_household_api import axiom_door1
from policyengine_household_api.axiom_door1 import (
    Door1Settings,
    bind_door1,
    calculation_scope,
    load_settings,
    request_tier,
)
from policyengine_household_common.routing_metadata import (
    RESOLVED_CHANNEL_ENVIRON_KEY,
)
from tests.fixtures.axiom_door1 import (
    FakeMode,
    enabled_settings,
    fake_countries,
    install_fake_policyengine_axiom,
)


pytestmark = pytest.mark.usefixtures("door1_reset")


def _request_context(channel=None):
    app = flask.Flask(__name__)
    overrides = {}
    if channel is not None:
        overrides[RESOLVED_CHANNEL_ENVIRON_KEY] = channel
    return app.test_request_context(
        "/us/calculate", method="POST", environ_overrides=overrides
    )


def _bind(monkeypatch, settings=None, **fake_options):
    axiom = install_fake_policyengine_axiom(monkeypatch, **fake_options)
    state = bind_door1(fake_countries(), settings or enabled_settings())
    return axiom, state


# settings -------------------------------------------------------------------


def test_default_config_leaves_door1_off():
    settings = load_settings()

    assert settings == Door1Settings()
    assert settings.enabled is False
    assert settings.serve_channels == {"frontier"}
    assert settings.shadow_channels == set()
    assert settings.countries == {"us"}


def test_settings_accept_the_env_var_forms():
    values = {
        "axiom_door1.enabled": "true",
        "axiom_door1.mode": "COMPARE",
        "axiom_door1.serve_channels": "frontier, current",
        "axiom_door1.clients": "abc,def",
        "axiom_door1.shadow_channels": "frontier",
    }

    settings = load_settings(lambda key, default: values.get(key, default))

    assert settings.enabled is True
    assert settings.mode == "compare"
    assert settings.serve_channels == {"frontier", "current"}
    assert settings.clients == {"abc", "def"}
    assert settings.shadow_channels == {"frontier"}


# per-request selection ------------------------------------------------------


@pytest.mark.parametrize(
    "country_id, channel, client_id, clients, tier",
    [
        ("us", "frontier", "abc", (), "selected"),
        ("us", "current", "abc", (), "unselected"),
        ("us", None, "abc", (), "unselected"),
        ("uk", "frontier", "abc", (), "unselected"),
        ("us", "frontier", "abc", ("abc",), "selected"),
        ("us", "frontier", "xyz", ("abc",), "unselected"),
        ("us", "frontier", None, ("abc",), "unselected"),
    ],
)
def test_without_shadow_channels_a_request_is_served_or_off(
    country_id, channel, client_id, clients, tier
):
    settings = enabled_settings(clients=frozenset(clients))

    assert (
        request_tier(
            settings,
            country_id=country_id,
            resolved_channel=channel,
            client_id=client_id,
        )
        == tier
    )


@pytest.mark.parametrize(
    "country_id, channel, client_id, tier",
    [
        # A listed client on a serve channel: the serving tier wins.
        ("us", "frontier", "abc", "selected"),
        # Every other frontier request runs Axiom in shadow only.
        ("us", "frontier", "xyz", "shadow"),
        # No client id (``/calculate_demo``): shadow too.
        ("us", "frontier", None, "shadow"),
        # Channels outside both tiers, and other countries, stay off.
        ("us", "current", "abc", "unselected"),
        ("us", None, "xyz", "unselected"),
        ("uk", "frontier", "xyz", "unselected"),
    ],
)
def test_shadow_tier_covers_the_rest_of_its_channels(
    country_id, channel, client_id, tier
):
    settings = enabled_settings(
        clients=frozenset({"abc"}),
        shadow_channels=frozenset({"frontier"}),
    )

    assert (
        request_tier(
            settings,
            country_id=country_id,
            resolved_channel=channel,
            client_id=client_id,
        )
        == tier
    )


def test_without_a_client_list_the_serving_tier_takes_the_whole_channel():
    settings = enabled_settings(shadow_channels=frozenset({"frontier"}))

    assert (
        request_tier(
            settings,
            country_id="us",
            resolved_channel="frontier",
            client_id="xyz",
        )
        == "selected"
    )


# bind -----------------------------------------------------------------------


def test_disabled_bind_never_imports_policyengine_axiom(monkeypatch):
    # An import would fail: a None entry in sys.modules raises ImportError.
    monkeypatch.setitem(sys.modules, "policyengine_axiom", None)

    state = bind_door1(fake_countries(), Door1Settings())

    assert state.bound is False
    assert state.reason == "disabled by config"


def test_missing_package_leaves_pe_answering(monkeypatch):
    monkeypatch.setitem(sys.modules, "policyengine_axiom", None)

    state = bind_door1(fake_countries(), enabled_settings())

    assert state.bound is False
    assert "not installed" in state.reason


@pytest.mark.parametrize("mode", ["strict", "off", "max"])
def test_bind_refuses_modes_a_serving_host_must_not_use(monkeypatch, mode):
    axiom, state = _bind(monkeypatch, enabled_settings(mode=mode))

    assert state.bound is False
    assert axiom.calls == []


def test_bind_refuses_a_provider_without_a_request_level_cap(monkeypatch):
    axiom, state = _bind(monkeypatch, request_cap=False)

    assert state.bound is False
    assert "request-level mode cap" in state.reason
    assert not [call for call in axiom.calls if call[0] == "apply"]


def test_bind_sets_the_fail_closed_default_before_binding(monkeypatch):
    axiom, state = _bind(monkeypatch)

    assert state.bound is True
    assert state.bound_countries == {"us"}
    assert axiom.calls == [
        ("default", "off"),
        ("manifests", "files"),
        ("apply", "us-system", ("manifest",), FakeMode.COMPARE),
    ]


def test_bind_logs_both_tiers(monkeypatch):
    _, state = _bind(
        monkeypatch,
        enabled_settings(
            clients=frozenset({"abc"}),
            shadow_channels=frozenset({"frontier"}),
        ),
    )

    assert state.reason.startswith(
        "mode compare; serve frontier (1 listed client(s)); shadow frontier; "
    )


def test_bind_runs_once_per_process(monkeypatch):
    axiom, _ = _bind(monkeypatch)
    bind_door1(fake_countries(), enabled_settings())

    assert len([call for call in axiom.calls if call[0] == "apply"]) == 1


def test_a_bind_error_leaves_pe_answering(monkeypatch):
    _, state = _bind(monkeypatch, apply_error=RuntimeError("no corpus root"))

    assert state.bound is False
    assert "bind failed: RuntimeError: no corpus root" in state.reason


def test_nothing_bound_means_door1_is_not_bound(monkeypatch):
    _, state = _bind(monkeypatch, bound=())

    assert state.bound is False
    assert "nothing bound" in state.reason


# calculation scope ----------------------------------------------------------


def test_scope_is_a_no_op_when_door1_is_not_bound():
    with _request_context("frontier"):
        with calculation_scope("us"):
            pass

    assert axiom_door1.state().bound is False


def test_frontier_request_may_get_axiom_answers(monkeypatch):
    axiom, _ = _bind(monkeypatch)
    monkeypatch.setattr(axiom_door1, "_client_id", lambda: "client-1")
    del axiom.calls[:]

    with _request_context("frontier"):
        with calculation_scope("us"):
            axiom.calls.append(("calculate",))

    assert axiom.calls == [
        ("enter", "client-1", "compare"),
        ("calculate",),
        ("exit", "client-1", "compare"),
    ]


@pytest.mark.parametrize("mode", ["shadow", "compare", "on"])
def test_fail_closed_default_does_not_turn_the_serving_tier_off(
    monkeypatch, mode
):
    """policyengine-axiom: inside a request context, ``mode=None`` falls
    back to the process default (``off``). The serving tier must pass the
    bind-time mode itself, or no request could ever reach Axiom."""
    axiom, _ = _bind(monkeypatch, enabled_settings(mode=mode))
    monkeypatch.setattr(axiom_door1, "_client_id", lambda: "client-1")
    assert axiom.default_mode == "off"

    with _request_context("frontier"):
        with calculation_scope("us"):
            pass

    assert axiom.effective_caps == [mode]


@pytest.mark.parametrize("channel", ["current", None])
def test_other_requests_run_with_the_provider_off(monkeypatch, channel):
    axiom, _ = _bind(monkeypatch)
    monkeypatch.setattr(axiom_door1, "_client_id", lambda: "client-1")
    del axiom.calls[:]

    with _request_context(channel):
        with calculation_scope("us"):
            pass

    assert axiom.calls[0] == ("enter", "client-1", "off")


@pytest.mark.parametrize(
    "channel, client_id, cap, tier",
    [
        ("frontier", "listed", "compare", "selected"),
        ("frontier", "other", "shadow", "shadow"),
        ("frontier", None, "shadow", "shadow"),
        ("current", "listed", "off", "unselected"),
        ("current", "other", "off", "unselected"),
        (None, "listed", "off", "unselected"),
    ],
)
def test_each_tier_reaches_the_provider_as_a_request_cap(
    monkeypatch, channel, client_id, cap, tier
):
    axiom, _ = _bind(
        monkeypatch,
        enabled_settings(
            clients=frozenset({"listed"}),
            shadow_channels=frozenset({"frontier"}),
        ),
    )
    attributes = []
    monkeypatch.setattr(axiom_door1, "_client_id", lambda: client_id)
    monkeypatch.setattr(
        axiom_door1,
        "_set_observability_attribute",
        lambda key, value: attributes.append((key, value)),
    )
    del axiom.calls[:]

    with _request_context(channel):
        with calculation_scope("us"):
            axiom.calls.append(("calculate",))

    assert axiom.calls == [
        ("enter", client_id, cap),
        ("calculate",),
        ("exit", client_id, cap),
    ]
    assert axiom.effective_caps == [cap]
    assert attributes == [("axiom_door1", tier)]


def test_unbound_country_is_untouched(monkeypatch):
    axiom, _ = _bind(monkeypatch)
    del axiom.calls[:]

    with _request_context("frontier"):
        with calculation_scope("uk"):
            pass

    assert axiom.calls == []


def test_a_scope_error_still_calculates(monkeypatch):
    axiom, _ = _bind(monkeypatch)
    axiom.request_error = RuntimeError("context failed")
    ran = []

    with _request_context("frontier"):
        with calculation_scope("us"):
            ran.append(True)

    assert ran == [True]


def test_a_calculation_error_propagates_and_closes_the_scope(monkeypatch):
    axiom, _ = _bind(monkeypatch)
    monkeypatch.setattr(axiom_door1, "_client_id", lambda: None)
    del axiom.calls[:]

    with _request_context("frontier"):
        with pytest.raises(ValueError):
            with calculation_scope("us"):
                raise ValueError("bad household")

    assert axiom.calls[-1] == ("exit", None, "compare")


# per-container runtime ------------------------------------------------------


def test_runtime_configuration_sets_this_containers_sink(
    monkeypatch, tmp_path
):
    axiom, _ = _bind(monkeypatch)
    monkeypatch.setenv("PE_AXIOM_CONTROL", "restored-after-the-test")

    axiom_door1.configure_door1_runtime(
        sink_dir=tmp_path / "sink" / "container-1",
        control_path=tmp_path / "control.json",
    )

    assert axiom.logs[0].aggregates.sink == tmp_path / "sink" / "container-1"
    assert os.environ["PE_AXIOM_CONTROL"] == str(tmp_path / "control.json")


def test_flush_never_raises(monkeypatch):
    axiom, _ = _bind(monkeypatch)
    axiom.logs[0].aggregates.fail = True

    axiom_door1.flush_door1()

    axiom.logs[0].aggregates.fail = False
    axiom_door1.flush_door1()
    assert axiom.logs[0].aggregates.flushes == 1
