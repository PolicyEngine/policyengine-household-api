"""Structural isolation guard for the analytics writer's environment.

Meaningful only in this member's own dependency closure
(`uv sync --package policyengine-household-analytics-api`): asserts the
modules that crashed the writer in issue #1603 are not merely un-imported
but uninstallable-by-declaration. Skipped in the fat all-packages dev
environment, where numpy is legitimately present.
"""

from importlib.util import find_spec

import pytest

HEAVY_MODULES = ("numpy", "modal", "policyengine_core", "policyengine_us")


@pytest.mark.skipif(
    find_spec("policyengine_us") is not None,
    reason="running in the fat all-packages environment",
)
def test_writer_environment_excludes_heavy_modules():
    present = [m for m in HEAVY_MODULES if find_spec(m) is not None]
    assert not present, (
        "The analytics writer environment must not contain heavy modules; "
        f"found installed: {present}"
    )


def test_writer_app_imports_and_serves_liveness():
    from policyengine_household_analytics_api.app import (
        create_analytics_writer_app,
    )

    app = create_analytics_writer_app(initialize_db=False)
    response = app.test_client().get("/liveness_check")

    assert response.status_code == 200
