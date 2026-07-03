from __future__ import annotations

from functools import cache

from google.api_core.exceptions import AlreadyExists
from google.cloud import tasks_v2
from google.protobuf import duration_pb2

from policyengine_household_api.analytics.config import (
    cloud_tasks_analytics_config,
)
from policyengine_household_api.analytics.events import CalculateAnalyticsEvent


@cache
def _cloud_tasks_client() -> tasks_v2.CloudTasksClient:
    return tasks_v2.CloudTasksClient()


def enqueue_calculate_analytics_event(
    event: CalculateAnalyticsEvent,
    *,
    client: tasks_v2.CloudTasksClient | None = None,
) -> None:
    config = cloud_tasks_analytics_config()
    cloud_tasks_client = client or _cloud_tasks_client()
    parent = cloud_tasks_client.queue_path(
        config.project,
        config.location,
        config.queue,
    )
    task_name = cloud_tasks_client.task_path(
        config.project,
        config.location,
        config.queue,
        event.context.request_uuid,
    )
    task = {
        "name": task_name,
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": config.target_url,
            "headers": {"Content-Type": "application/json"},
            "body": event.model_dump_json().encode("utf-8"),
            "oidc_token": {
                "service_account_email": config.service_account_email,
                "audience": config.oidc_audience,
            },
        },
        "dispatch_deadline": duration_pb2.Duration(
            seconds=config.dispatch_deadline_seconds
        ),
    }
    try:
        cloud_tasks_client.create_task(parent=parent, task=task)
    except AlreadyExists:
        return
