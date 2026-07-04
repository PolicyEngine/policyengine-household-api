import sys
import types

import pytest

from policyengine_household_common.dispatch_codec import (
    encode_dispatch_response,
)
from policyengine_household_modal import warm_worker


class _FakeWorker:
    def __init__(self, results):
        self._results = results
        self.calls = 0

    def handle_household_request_remote(self, payload):
        self.calls += 1
        result = self._results[min(self.calls - 1, len(self._results) - 1)]
        if isinstance(result, Exception):
            raise result
        return result


def _install_fake_modal(monkeypatch, worker: _FakeWorker):
    class _FakeMethod:
        def remote(self, payload):
            return worker.handle_household_request_remote(payload)

    class _FakeInstance:
        handle_household_request = _FakeMethod()

    class _FakeCls:
        @staticmethod
        def from_name(app_name, cls_name, environment_name=None):
            assert cls_name == "HouseholdWorker"
            return lambda: _FakeInstance()

    fake_modal = types.SimpleNamespace(Cls=_FakeCls)
    monkeypatch.setitem(sys.modules, "modal", fake_modal)


def test_warm_worker_returns_once_new_version_serves(monkeypatch):
    ok = encode_dispatch_response(
        {"status_code": 200, "headers": {}, "body": b"OK"}
    )
    worker = _FakeWorker([RuntimeError("snapshotting"), ok])
    _install_fake_modal(monkeypatch, worker)

    warm_worker.warm_worker_app(
        "household-api-test-worker",
        modal_environment="staging",
        timeout_seconds=60,
        sleep=lambda _s: None,
        monotonic=iter(range(0, 600, 5)).__next__,
    )

    assert worker.calls == 2


def test_warm_worker_fails_after_deadline(monkeypatch):
    bad = encode_dispatch_response(
        {"status_code": 503, "headers": {}, "body": b""}
    )
    worker = _FakeWorker([bad])
    _install_fake_modal(monkeypatch, worker)

    with pytest.raises(SystemExit, match="did not serve within"):
        warm_worker.warm_worker_app(
            "household-api-test-worker",
            modal_environment="staging",
            timeout_seconds=20,
            sleep=lambda _s: None,
            monotonic=iter(range(0, 600, 5)).__next__,
        )

    assert worker.calls >= 1
