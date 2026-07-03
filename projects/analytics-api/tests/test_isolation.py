"""Structural isolation guard for the analytics writer's environment.

Meaningful only in this member's own dependency closure
(`uv sync --package policyengine-household-analytics-api`): asserts the
modules that crashed the writer in issue #1603 are not merely un-imported
but uninstallable-by-declaration. Skipped in the fat all-packages dev
environment, where numpy is legitimately present.
"""

from importlib.metadata import PackageNotFoundError, version

import pytest

HEAVY_DISTRIBUTIONS = (
    "numpy",
    "modal",
    "policyengine-core",
    "policyengine-us",
)


def _installed(distribution: str) -> bool:
    try:
        version(distribution)
    except PackageNotFoundError:
        return False
    return True


@pytest.mark.skipif(
    _installed("policyengine-us"),
    reason="running in the fat all-packages environment",
)
def test_writer_environment_excludes_heavy_distributions():
    present = [d for d in HEAVY_DISTRIBUTIONS if _installed(d)]
    assert not present, (
        "The analytics writer environment must not contain heavy "
        f"distributions; found installed: {present}"
    )


def test_writer_app_imports_and_serves_liveness():
    from policyengine_household_analytics_api.app import (
        create_analytics_writer_app,
    )

    app = create_analytics_writer_app(initialize_db=False)
    response = app.test_client().get("/liveness_check")

    assert response.status_code == 200
