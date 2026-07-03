from datetime import datetime, timezone
import logging
import subprocess
import sys
from unittest.mock import MagicMock

from policyengine_household_analytics.events import CalculateAnalyticsEvent
from policyengine_household_api.failover.cloud_run_analytics_writer import (
    create_analytics_writer_app,
)
from policyengine_household_common.models.analytics import (
    AnalyticsContext,
    AnalyticsHttpMethod,
)


def _event_payload():
    event = CalculateAnalyticsEvent(
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
    return event.model_dump(mode="json")


def test_analytics_writer_liveness_check():
    app = create_analytics_writer_app(initialize_db=False)

    response = app.test_client().get("/liveness_check")

    assert response.status_code == 200
    assert response.text == "OK"


def test_analytics_writer_persists_valid_event():
    persist = MagicMock()
    app = create_analytics_writer_app(
        persist_event=persist,
        initialize_db=False,
    )

    response = app.test_client().post(
        "/internal/analytics/calculate/write",
        json=_event_payload(),
    )

    assert response.status_code == 200
    assert response.get_json()["request_uuid"] == (
        "018f79e7-6ee3-7621-9eda-6d29cf0cf910"
    )
    persist.assert_called_once()
    assert persist.call_args.args[0].context.request_uuid == (
        "018f79e7-6ee3-7621-9eda-6d29cf0cf910"
    )


def test_analytics_writer_rejects_invalid_payload():
    persist = MagicMock()
    app = create_analytics_writer_app(
        persist_event=persist,
        initialize_db=False,
    )

    response = app.test_client().post(
        "/internal/analytics/calculate/write",
        json={"schema_version": 1},
    )

    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_analytics_event"
    persist.assert_not_called()


def test_analytics_writer_db_failure_returns_500_for_cloud_tasks_retry(
    caplog,
):
    def fail(_event):
        raise RuntimeError("database unavailable")

    app = create_analytics_writer_app(
        persist_event=fail,
        initialize_db=False,
    )
    caplog.set_level(
        logging.WARNING,
        logger="policyengine_household_api.failover.cloud_run_analytics_writer",
    )

    response = app.test_client().post(
        "/internal/analytics/calculate/write",
        json=_event_payload(),
    )

    assert response.status_code == 500
    assert response.get_json()["code"] == "analytics_write_failed"
    assert "Failed to persist calculate analytics event" in caplog.text


def test_analytics_writer_import_chain_stays_slim():
    """The writer image installs only the analytics-writer dependency group.

    Importing the writer must not pull modules excluded from that group
    (numpy via utils.json, country model packages via calculation code), or
    the deployed writer crash-loops at gunicorn worker boot.
    """
    heavy_modules = (
        "numpy",
        "policyengine_core",
        "policyengine_uk",
        "policyengine_us",
    )
    probe = (
        "import sys\n"
        "import policyengine_household_api.failover."
        "cloud_run_analytics_writer\n"
        "import policyengine_household_analytics.persistence\n"
        f"heavy = [m for m in {heavy_modules!r} if m in sys.modules]\n"
        "assert not heavy, f'writer import pulled heavy modules: {heavy}'\n"
    )

    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
