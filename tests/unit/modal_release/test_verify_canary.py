import modal
import pytest

from policyengine_household_modal.verify_canary import verify_canary_app


def test_verify_canary_calls_deployed_ping(monkeypatch):
    calls = []

    class StubFunction:
        def remote(self):
            calls.append(("remote",))
            return {"ok": True, "service": "household-api-modal-canary"}

    def from_name(app_name, function_name, *, environment_name):
        calls.append(("from_name", app_name, function_name, environment_name))
        return StubFunction()

    monkeypatch.setattr(
        modal.Function,
        "from_name",
        staticmethod(from_name),
    )

    result = verify_canary_app(
        "test-canary",
        modal_environment="testing",
    )

    assert result == {
        "ok": True,
        "service": "household-api-modal-canary",
    }
    assert calls == [
        ("from_name", "test-canary", "ping", "testing"),
        ("remote",),
    ]


def test_verify_canary_rejects_invalid_ping_response(monkeypatch):
    class StubFunction:
        def remote(self):
            return {"ok": False}

    monkeypatch.setattr(
        modal.Function,
        "from_name",
        staticmethod(lambda *_args, **_kwargs: StubFunction()),
    )

    with pytest.raises(RuntimeError, match="invalid ping response"):
        verify_canary_app(
            "test-canary",
            modal_environment="testing",
        )
