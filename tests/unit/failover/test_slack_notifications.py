import json
import logging

from policyengine_household_failover.slack_notifications import (
    SLACK_COOLDOWN_SECONDS_ENV,
    SLACK_TIMEOUT_SECONDS_ENV,
    SLACK_WEBHOOK_URL_ENV,
    SlackFailoverNotifier,
)


WEBHOOK_URL = "https://example.com/webhook"


class RecordingExecutor:
    def __init__(self, *, run_submitted=False):
        self.run_submitted = run_submitted
        self.calls = []

    def submit(self, function, *args):
        self.calls.append((function, args))
        if self.run_submitted:
            function(*args)


class FailingOnceExecutor:
    def __init__(self):
        self.calls = []
        self.fail_next = True

    def submit(self, function, *args):
        self.calls.append((function, args))
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("executor closed")


class FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


def test_notify_noops_without_webhook_url(monkeypatch):
    monkeypatch.delenv(SLACK_WEBHOOK_URL_ENV, raising=False)
    executor = RecordingExecutor()
    notifier = SlackFailoverNotifier(executor=executor)

    submitted = notifier.notify("modal_circuit_opened", channel="current")

    assert submitted is False
    assert executor.calls == []


def test_notify_ignores_non_lifecycle_events(monkeypatch):
    monkeypatch.setenv(
        SLACK_WEBHOOK_URL_ENV,
        WEBHOOK_URL,
    )
    executor = RecordingExecutor()
    notifier = SlackFailoverNotifier(executor=executor)

    submitted = notifier.notify("modal_request_failed", channel="current")

    assert submitted is False
    assert executor.calls == []


def test_notify_submits_async_payload_with_configured_timeout(monkeypatch):
    monkeypatch.setenv(
        SLACK_WEBHOOK_URL_ENV,
        WEBHOOK_URL,
    )
    monkeypatch.setenv(SLACK_TIMEOUT_SECONDS_ENV, "4.5")
    monkeypatch.setenv("OBSERVABILITY_ENVIRONMENT", "production")
    monkeypatch.setenv("K_SERVICE", "household-api-gateway")
    monkeypatch.setenv("K_REVISION", "household-api-gateway-00042")
    executor = RecordingExecutor()

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("urlopen should run asynchronously")

    notifier = SlackFailoverNotifier(
        executor=executor,
        urlopen=fail_if_called,
    )

    submitted = notifier.notify(
        "fallback_selected",
        channel="current",
        reason="modal_canary_confirmed",
    )

    assert submitted is True
    assert len(executor.calls) == 1
    _function, args = executor.calls[0]
    webhook_url, payload, timeout_seconds = args
    assert webhook_url == WEBHOOK_URL
    assert timeout_seconds == 4.5
    assert payload["text"] == (
        "Household API failover: Cloud Run fallback selected"
    )
    field_text = "\n".join(
        field["text"] for field in payload["blocks"][1]["fields"]
    )
    assert "*Environment*\nproduction" in field_text
    assert "*Event*\nfallback_selected" in field_text
    assert "*Channel*\ncurrent" in field_text
    assert "*Reason*\nmodal_canary_confirmed" in field_text
    assert "*Backend*\ncloud_run" in field_text
    assert "*Cloud Run service*\nhousehold-api-gateway" in field_text
    assert "*Cloud Run revision*\nhousehold-api-gateway-00042" in field_text


def test_notify_posts_json_payload_when_executor_runs(monkeypatch):
    monkeypatch.setenv(
        SLACK_WEBHOOK_URL_ENV,
        WEBHOOK_URL,
    )
    captured = {}

    def fake_urlopen(request, *, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    notifier = SlackFailoverNotifier(
        executor=RecordingExecutor(run_submitted=True),
        urlopen=fake_urlopen,
    )

    submitted = notifier.notify("modal_circuit_recovered", channel="frontier")

    assert submitted is True
    assert captured["url"] == WEBHOOK_URL
    assert captured["timeout"] == 2.0
    assert captured["headers"]["Content-type"] == (
        "application/json; charset=utf-8"
    )
    assert captured["body"]["text"] == (
        "Household API failover: Modal circuit recovered"
    )


def test_notify_applies_cooldown_by_event_channel_and_reason(monkeypatch):
    monkeypatch.setenv(
        SLACK_WEBHOOK_URL_ENV,
        WEBHOOK_URL,
    )
    monkeypatch.setenv(SLACK_COOLDOWN_SECONDS_ENV, "300")
    clock = [1000.0]
    executor = RecordingExecutor()
    notifier = SlackFailoverNotifier(
        executor=executor,
        time_source=lambda: clock[0],
    )

    assert notifier.notify(
        "fallback_selected",
        channel="current",
        reason="modal_circuit_open",
    )
    assert not notifier.notify(
        "fallback_selected",
        channel="current",
        reason="modal_circuit_open",
    )
    assert notifier.notify(
        "fallback_selected",
        channel="frontier",
        reason="modal_circuit_open",
    )

    clock[0] += 301
    assert notifier.notify(
        "fallback_selected",
        channel="current",
        reason="modal_circuit_open",
    )
    assert len(executor.calls) == 3


def test_notify_does_not_start_cooldown_when_submission_fails(
    monkeypatch,
    caplog,
):
    monkeypatch.setenv(
        SLACK_WEBHOOK_URL_ENV,
        WEBHOOK_URL,
    )
    monkeypatch.setenv(SLACK_COOLDOWN_SECONDS_ENV, "300")
    executor = FailingOnceExecutor()
    notifier = SlackFailoverNotifier(executor=executor)

    with caplog.at_level(logging.WARNING):
        assert not notifier.notify(
            "fallback_selected",
            channel="current",
            reason="modal_circuit_open",
        )

    assert "Failed to submit Slack failover alert" in caplog.text
    assert notifier.notify(
        "fallback_selected",
        channel="current",
        reason="modal_circuit_open",
    )
    assert len(executor.calls) == 2


def test_notify_swallows_delivery_failure_without_logging_secret(
    monkeypatch,
    caplog,
):
    webhook_url = WEBHOOK_URL
    monkeypatch.setenv(SLACK_WEBHOOK_URL_ENV, webhook_url)

    def fail_urlopen(*_args, **_kwargs):
        raise RuntimeError(f"failed for {webhook_url}")

    notifier = SlackFailoverNotifier(
        executor=RecordingExecutor(run_submitted=True),
        urlopen=fail_urlopen,
    )

    with caplog.at_level(logging.WARNING):
        submitted = notifier.notify("backend_unavailable", channel="current")

    assert submitted is True
    assert "Failed to send Slack failover alert" in caplog.text
    assert webhook_url not in caplog.text
