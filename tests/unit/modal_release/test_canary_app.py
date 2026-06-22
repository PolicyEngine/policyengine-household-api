import importlib


def test_canary_payload_is_static_health_signal():
    from policyengine_household_api.modal_release import canary_app

    assert canary_app.canary_payload() == {
        "ok": True,
        "service": "household-api-modal-canary",
    }


def test_canary_function_options_are_lightweight(monkeypatch):
    monkeypatch.setenv(
        "HOUSEHOLD_MODAL_CANARY_APP_NAME",
        "household-canary-test",
    )
    from policyengine_household_api.modal_release import canary_app

    reloaded = importlib.reload(canary_app)
    options = reloaded.canary_function_options()

    assert reloaded.CANARY_APP_NAME == "household-canary-test"
    assert options["timeout"] == 10
    assert options["scaledown_window"] == 300
    assert len(options["secrets"]) == 1
