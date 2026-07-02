from datetime import datetime, timezone

from google.api_core.exceptions import AlreadyExists
from google.cloud import tasks_v2

from policyengine_household_api.analytics.config import (
    CloudTasksAnalyticsConfig,
)
from policyengine_household_api.analytics.events import CalculateAnalyticsEvent
from policyengine_household_api.models.analytics import (
    AnalyticsContext,
    AnalyticsHttpMethod,
)


class FakeCloudTasksClient:
    def __init__(self, *, fail_already_exists: bool = False):
        self.fail_already_exists = fail_already_exists
        self.created_tasks = []

    def queue_path(self, project, location, queue):
        return f"projects/{project}/locations/{location}/queues/{queue}"

    def task_path(self, project, location, queue, task):
        return (
            f"projects/{project}/locations/{location}/queues/{queue}"
            f"/tasks/{task}"
        )

    def create_task(self, *, parent, task):
        if self.fail_already_exists:
            raise AlreadyExists("already exists")
        self.created_tasks.append((parent, task))


def _event() -> CalculateAnalyticsEvent:
    return CalculateAnalyticsEvent(
        context=AnalyticsContext(
            client_id="client-1",
            request_uuid="018f79e7-6ee3-7621-9eda-6d29cf0cf910",
            api_version="0.1.0",
            endpoint="calculate",
            method=AnalyticsHttpMethod.POST,
            content_length_bytes=100,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            country_id="us",
            record_calculate_request=True,
        ),
        response_status_code=200,
    )


def _config() -> CloudTasksAnalyticsConfig:
    return CloudTasksAnalyticsConfig(
        project="policyengine-test",
        location="us-central1",
        queue="analytics-writes",
        target_url="https://writer.run.app/internal/analytics/calculate/write",
        service_account_email="tasks@policyengine-test.iam.gserviceaccount.com",
        oidc_audience="https://writer.run.app",
        dispatch_deadline_seconds=120,
    )


def test_enqueue_calculate_analytics_event_builds_http_task(monkeypatch):
    from policyengine_household_api.analytics import cloud_tasks

    monkeypatch.setattr(
        cloud_tasks,
        "cloud_tasks_analytics_config",
        _config,
    )
    client = FakeCloudTasksClient()

    cloud_tasks.enqueue_calculate_analytics_event(_event(), client=client)

    parent, task = client.created_tasks[0]
    assert parent == (
        "projects/policyengine-test/locations/us-central1/"
        "queues/analytics-writes"
    )
    assert task["name"].endswith("/tasks/018f79e7-6ee3-7621-9eda-6d29cf0cf910")
    assert task["http_request"]["http_method"] == tasks_v2.HttpMethod.POST
    assert task["http_request"]["url"] == (
        "https://writer.run.app/internal/analytics/calculate/write"
    )
    assert task["http_request"]["headers"] == {
        "Content-Type": "application/json"
    }
    assert task["http_request"]["oidc_token"] == {
        "service_account_email": (
            "tasks@policyengine-test.iam.gserviceaccount.com"
        ),
        "audience": "https://writer.run.app",
    }
    assert (
        b"018f79e7-6ee3-7621-9eda-6d29cf0cf910" in task["http_request"]["body"]
    )
    assert task["dispatch_deadline"].seconds == 120


def test_enqueue_calculate_analytics_event_treats_existing_task_as_success(
    monkeypatch,
):
    from policyengine_household_api.analytics import cloud_tasks

    monkeypatch.setattr(
        cloud_tasks,
        "cloud_tasks_analytics_config",
        _config,
    )
    client = FakeCloudTasksClient(fail_already_exists=True)

    cloud_tasks.enqueue_calculate_analytics_event(_event(), client=client)
