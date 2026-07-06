import itertools

import pytest

from policyengine_household_modal import warm_worker
from tests.fixtures.modal_fakes import (
    FakeModalNotFoundError,
    FakeWorkerDispatch,
    install_fake_modal,
)

# The raw result shape HouseholdWorker.handle_household_request returns
# (dispatch_to_flask_app output), not the Cloud Run dispatch codec.
OK_RESULT = {"status_code": 200, "body": b"OK", "headers": []}
UNAVAILABLE_RESULT = {"status_code": 503, "body": b"", "headers": []}


def fake_clock():
    return itertools.count(0, 10).__next__


def test_warm_worker_returns_once_new_version_serves(monkeypatch):
    worker = FakeWorkerDispatch(
        results=[RuntimeError("snapshotting"), OK_RESULT],
        expected_app_name="household-api-test-worker",
        expected_environment_name="staging",
    )
    install_fake_modal(monkeypatch, worker)

    warm_worker.warm_worker_app(
        "household-api-test-worker",
        modal_environment="staging",
        timeout_seconds=60,
        sleep=lambda _s: None,
        monotonic=fake_clock(),
    )

    assert worker.calls == 2
    # Each dispatch waits at most the remaining warm budget instead of
    # hanging indefinitely on a wedged container.
    assert worker.get_timeouts == [50, 30]


def test_warm_worker_fails_after_deadline(monkeypatch):
    worker = FakeWorkerDispatch(
        results=[UNAVAILABLE_RESULT],
        expected_app_name="household-api-test-worker",
        expected_environment_name="staging",
    )
    install_fake_modal(monkeypatch, worker)

    with pytest.raises(SystemExit, match="did not serve within 65s"):
        warm_worker.warm_worker_app(
            "household-api-test-worker",
            modal_environment="staging",
            timeout_seconds=65,
            sleep=lambda _s: None,
            monotonic=fake_clock(),
        )

    # The 10s-step fake clock and 65s budget yield exactly three attempts.
    assert worker.calls == 3


def test_warm_worker_falls_back_to_legacy_function_worker(monkeypatch):
    worker = FakeWorkerDispatch(
        results=[OK_RESULT],
        expected_app_name="household-api-test-worker",
        expected_environment_name="staging",
        cls_lookup_error=FakeModalNotFoundError("no HouseholdWorker class"),
    )
    install_fake_modal(monkeypatch, worker)

    warm_worker.warm_worker_app(
        "household-api-test-worker",
        modal_environment="staging",
        timeout_seconds=60,
        sleep=lambda _s: None,
        monotonic=fake_clock(),
    )

    assert worker.calls == 1


def test_warm_worker_fails_fast_when_app_is_missing(monkeypatch):
    worker = FakeWorkerDispatch(
        results=[],
        cls_lookup_error=FakeModalNotFoundError("no HouseholdWorker class"),
        function_lookup_error=FakeModalNotFoundError("no function"),
    )
    install_fake_modal(monkeypatch, worker)

    with pytest.raises(SystemExit, match="no dispatch entrypoint"):
        warm_worker.warm_worker_app(
            "no-such-app",
            modal_environment="staging",
            timeout_seconds=60,
            sleep=lambda _s: None,
            monotonic=fake_clock(),
        )

    # A missing app is permanent: no dispatch is attempted and no retry
    # budget is burned.
    assert worker.calls == 0
