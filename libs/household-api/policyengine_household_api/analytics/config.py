from __future__ import annotations

from dataclasses import dataclass

from policyengine_household_common.config_loader import get_config_value


@dataclass(frozen=True)
class CloudTasksAnalyticsConfig:
    project: str
    location: str
    queue: str
    target_url: str
    service_account_email: str
    oidc_audience: str
    dispatch_deadline_seconds: int


def cloud_tasks_analytics_config() -> CloudTasksAnalyticsConfig:
    project = str(get_config_value("analytics.cloud_tasks.project", "") or "")
    location = str(
        get_config_value("analytics.cloud_tasks.location", "") or ""
    )
    queue = str(get_config_value("analytics.cloud_tasks.queue", "") or "")
    target_url = str(
        get_config_value("analytics.cloud_tasks.target_url", "") or ""
    )
    service_account_email = str(
        get_config_value(
            "analytics.cloud_tasks.service_account_email",
            "",
        )
        or ""
    )
    oidc_audience = str(
        get_config_value("analytics.cloud_tasks.oidc_audience", "")
        or target_url
    )
    dispatch_deadline_seconds = int(
        get_config_value(
            "analytics.cloud_tasks.dispatch_deadline_seconds",
            300,
        )
    )

    missing = [
        name
        for name, value in {
            "analytics.cloud_tasks.project": project,
            "analytics.cloud_tasks.location": location,
            "analytics.cloud_tasks.queue": queue,
            "analytics.cloud_tasks.target_url": target_url,
            "analytics.cloud_tasks.service_account_email": (
                service_account_email
            ),
            "analytics.cloud_tasks.oidc_audience": oidc_audience,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(
            "Missing analytics Cloud Tasks configuration: "
            + ", ".join(missing)
        )

    return CloudTasksAnalyticsConfig(
        project=project,
        location=location,
        queue=queue,
        target_url=target_url,
        service_account_email=service_account_email,
        oidc_audience=oidc_audience,
        dispatch_deadline_seconds=dispatch_deadline_seconds,
    )
