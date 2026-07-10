import importlib
import os
from types import SimpleNamespace

import pytest

from policyengine_household_api.deployment import (
    PACKAGE_VERSIONS_ENV,
    country_package_install_specs,
    deployment_package_versions_from_env,
)


pytestmark = pytest.mark.usefixtures("worker_app")


@pytest.fixture
def worker_app(monkeypatch):
    monkeypatch.setenv("MODAL_ENVIRONMENT", "testing")
    from policyengine_household_modal import worker_app

    return importlib.reload(worker_app)


def test_worker_function_options_keep_main_workers_warm(worker_app):
    options = worker_app.worker_function_options(modal_environment="main")

    assert options["min_containers"] == 3
    assert options["buffer_containers"] == 2
    assert options["scaledown_window"] == 600


def test_worker_function_options_do_not_keep_staging_workers_warm():
    from policyengine_household_modal.worker_app import (
        worker_function_options,
    )

    options = worker_function_options(modal_environment="staging")

    assert "min_containers" not in options
    assert "buffer_containers" not in options
    assert options["scaledown_window"] == 300


def test_worker_function_options_do_not_keep_workers_warm_without_env(
    monkeypatch,
):
    monkeypatch.delenv("MODAL_ENVIRONMENT", raising=False)
    from policyengine_household_modal.worker_app import (
        worker_function_options,
    )

    with pytest.raises(RuntimeError, match="MODAL_ENVIRONMENT"):
        worker_function_options(modal_environment=None)


def test_worker_function_options_enable_memory_snapshot_in_all_envs(
    worker_app,
):
    for environment in ("main", "staging", "testing"):
        options = worker_app.worker_function_options(
            modal_environment=environment
        )
        assert options["enable_memory_snapshot"] is True, (
            f"enable_memory_snapshot must be True in `{environment}` "
            "so cold starts restore from a memory snapshot instead of "
            "re-running the ~45s policyengine import chain"
        )


def test_household_worker_exposes_snapshot_entrypoint(worker_app):
    """The class must declare its snapshot-time hook so heavy imports
    are captured in the memory snapshot rather than running per cold
    start."""
    worker_cls = worker_app.HouseholdWorker
    assert hasattr(worker_cls, "load_flask_app")
    assert hasattr(worker_cls, "handle_household_request")


def test_snapshot_hook_prewarms_parameter_caches(worker_app):
    """The snap=True hook must call prewarm_parameter_caches() so the
    populated parameter at-instant caches ride the memory snapshot;
    dropping the call silently reintroduces the 60-105s first-request
    build that flakes the Cloud Run staging lanes (issue #1624)."""
    import inspect

    source = inspect.getsource(worker_app)
    assert "prewarm_parameter_caches()" in source


def test_household_worker_exposes_post_snapshot_reset_hook(worker_app):
    """The class must declare a post-restore hook so network state
    captured in the memory snapshot (SQLAlchemy pool, Cloud SQL
    Connector) gets reset on every container start. Modal preserves
    Python object state but not live TCP sockets across snapshots."""
    worker_cls = worker_app.HouseholdWorker
    assert hasattr(worker_cls, "reset_post_snapshot_state")


def test_post_snapshot_reset_restarts_observability_after_credentials(
    worker_app, monkeypatch
):
    """Memory snapshots preserve neither threads nor /tmp: the queued
    log transport's listener thread dies at snapshot time, so a restored
    container must rebuild its log destinations or silently drop every
    Google-bound record — and only after the credentials file is
    re-materialized, so the fresh Google client can authenticate."""
    calls = []
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/tmp/stale.json")
    monkeypatch.setattr(
        worker_app,
        "configure_google_credentials",
        lambda: calls.append("credentials"),
    )
    monkeypatch.setattr(
        worker_app,
        "restart_observability",
        lambda: calls.append("restart_observability"),
    )

    worker_app.reset_post_snapshot_process_state(
        SimpleNamespace(extensions={})
    )

    assert calls == ["credentials", "restart_observability"]
    assert "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ


def test_worker_concurrency_options_set_max_inputs(worker_app):
    """Heavy customer calculates cost 12-50 CPU-seconds each; a low input
    concurrency cap bounds in-container contention and limits the
    collateral of Modal's cancel-shuts-down-the-container semantics
    (issue #1609)."""
    assert worker_app.worker_concurrency_options()["max_inputs"] == 3


def test_worker_concurrency_options_set_target_inputs(worker_app):
    """A low autoscale target adds capacity before containers saturate,
    so simultaneous heavy requests spread across containers instead of
    piling onto one (issue #1609)."""
    assert worker_app.worker_concurrency_options()["target_inputs"] == 2


def test_worker_function_options_reserve_cpu(worker_app):
    """Workers reserve a 1-core CPU floor in every environment. Modal
    guarantees only 0.125 cores by default (rest is best-effort burst), so
    containers running simultaneous heavy calculates starve and time out,
    surfacing as 503 backend_unavailable (notably the Amplifi household on
    staging). 1.0 is a cost-balanced floor vs the 2.0 dropped in #1610."""
    for environment in ("main", "staging", "testing"):
        options = worker_app.worker_function_options(
            modal_environment=environment
        )
        assert options["cpu"] == 1.0


def test_worker_function_options_execution_budget(worker_app):
    """300s covers the worst legitimate heavy calculate at 2-way
    concurrency with ~3x headroom; the gateway budget must stay above it
    so the worker's own timeout resolves first (issue #1609)."""
    for environment in ("main", "staging", "testing"):
        options = worker_app.worker_function_options(
            modal_environment=environment
        )
        assert options["timeout"] == 300


def test_worker_function_options_do_not_use_deprecated_concurrency_kwarg(
    worker_app,
):
    for environment in ("main", "staging", "testing"):
        options = worker_app.worker_function_options(
            modal_environment=environment
        )
        assert "allow_concurrent_inputs" not in options, (
            "`allow_concurrent_inputs` is deprecated; use "
            f"`@modal.concurrent` for `{environment}` worker concurrency"
        )


def test_worker_function_options_max_containers_capped_in_all_envs(
    worker_app,
):
    """A hard ceiling on autoscale prevents runaway scaling from a buggy
    client or traffic spike from racking up unbounded cost."""
    for environment in ("main", "staging", "testing"):
        options = worker_app.worker_function_options(
            modal_environment=environment
        )
        assert options["max_containers"] == 100, (
            f"max_containers must be 100 in `{environment}` to bound "
            "autoscale cost"
        )


def test_country_package_install_specs_use_release_package_versions_only():
    assert country_package_install_specs(
        {
            "uk": "2.31.0",
            "us": "1.691.1",
            "ca": "0.96.3",
        }
    ) == [
        "policyengine_uk==2.31.0",
        "policyengine_us==1.691.1",
    ]


def test_deployment_package_versions_from_env(monkeypatch):
    monkeypatch.setenv(
        PACKAGE_VERSIONS_ENV,
        '{"uk":"2.31.0","us":"1.691.1","ca":"0.96.3"}',
    )

    assert deployment_package_versions_from_env() == {
        "uk": "2.31.0",
        "us": "1.691.1",
    }


def test_deployment_package_versions_from_env_rejects_non_object(
    monkeypatch,
):
    monkeypatch.setenv(PACKAGE_VERSIONS_ENV, '["us"]')

    with pytest.raises(RuntimeError, match="JSON object"):
        deployment_package_versions_from_env()
