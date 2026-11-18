"""The calculate endpoint selects each request for Door 1 by its channel."""

import json
import sys

import pytest

from policyengine_household_api import axiom_door1
from policyengine_household_common.config_loader import get_config_value
from policyengine_household_common.routing_metadata import (
    REQUESTED_VERSION_ENVIRON_KEY,
    RESOLVED_CHANNEL_ENVIRON_KEY,
)
from tests.fixtures.axiom_door1 import (
    FakeAxiom,
    build_fake_runtime,
    enabled_settings,
)
from tests.fixtures.country import (
    valid_household_requesting_ctc_calculation,
)


pytestmark = pytest.mark.usefixtures("door1_reset")

AUTH_HEADERS = {
    "Authorization": f"Bearer {get_config_value('auth.auth0.test_token')}",
}


@pytest.fixture
def door1_runtime(monkeypatch):
    """Door 1 bound for the US, with a recording provider runtime.

    No variable is bound in the real system: the endpoint's job is to open
    the right scope, and PolicyEngine's numbers must come back unchanged.
    """
    axiom = FakeAxiom()
    monkeypatch.setattr(
        axiom_door1,
        "_state",
        axiom_door1.Door1State(
            settings=enabled_settings(),
            bound_countries=frozenset({"us"}),
            reason="test",
            runtime=build_fake_runtime(axiom),
        ),
    )
    return axiom


def _calculate(client, channel):
    response = client.post(
        "/us/calculate",
        json={"household": valid_household_requesting_ctc_calculation},
        headers=AUTH_HEADERS,
        environ_overrides={
            REQUESTED_VERSION_ENVIRON_KEY: channel,
            RESOLVED_CHANNEL_ENVIRON_KEY: channel,
        },
    )
    assert response.status_code == 200
    return json.loads(response.data)


def test_default_config_request_never_touches_the_provider(
    client, monkeypatch
):
    """With the default config Door 1 is not bound: a calculate request,
    even on frontier, runs the plain PolicyEngine path and never imports
    policyengine-axiom (a ``None`` entry makes any import raise)."""
    monkeypatch.setitem(sys.modules, "policyengine_axiom", None)
    monkeypatch.setitem(sys.modules, "policyengine_axiom.runtime", None)
    assert axiom_door1.load_settings().enabled is False
    assert axiom_door1.state().bound is False

    result = _calculate(client, "frontier")

    assert result["status"] == "ok"
    assert axiom_door1.state().bound is False
    assert axiom_door1.state().reason == "not bound"


def test_frontier_request_opens_a_serving_scope(client, door1_runtime):
    _calculate(client, "frontier")

    assert [call[0] for call in door1_runtime.calls] == ["enter", "exit"]
    # The bind-time mode, passed explicitly (``None`` would fall back to the
    # process default ``off`` in policyengine-axiom).
    assert door1_runtime.calls[0][2] == "compare"


def test_current_request_runs_with_the_provider_off(client, door1_runtime):
    _calculate(client, "current")

    assert door1_runtime.calls[0][2] == "off"


def test_unlisted_frontier_client_runs_in_shadow(client, monkeypatch):
    """Serving only for listed clients, shadow for the rest of
    frontier, and current untouched."""
    axiom = FakeAxiom()
    monkeypatch.setattr(
        axiom_door1,
        "_state",
        axiom_door1.Door1State(
            settings=enabled_settings(
                clients=frozenset({"a-listed-client"}),
                shadow_channels=frozenset({"frontier"}),
            ),
            bound_countries=frozenset({"us"}),
            reason="test",
            runtime=build_fake_runtime(axiom),
        ),
    )

    _calculate(client, "frontier")
    _calculate(client, "current")

    entered = [call for call in axiom.calls if call[0] == "enter"]
    assert [call[2] for call in entered] == ["shadow", "off"]


def test_door1_scope_leaves_the_response_unchanged(client, monkeypatch):
    plain = _calculate(client, "frontier")
    axiom = FakeAxiom()
    monkeypatch.setattr(
        axiom_door1,
        "_state",
        axiom_door1.Door1State(
            settings=enabled_settings(),
            bound_countries=frozenset({"us"}),
            reason="test",
            runtime=build_fake_runtime(axiom),
        ),
    )

    with_door1 = _calculate(client, "frontier")

    assert with_door1 == plain
