import importlib

import pytest

from policyengine_household_api.modal_release.images import (
    PACKAGE_VERSIONS_ENV,
    country_package_install_specs,
    deployment_package_versions_from_env,
)


pytestmark = pytest.mark.usefixtures("worker_app")


@pytest.fixture
def worker_app(monkeypatch):
    monkeypatch.setenv("MODAL_ENVIRONMENT", "testing")
    from policyengine_household_api.modal_release import worker_app

    return importlib.reload(worker_app)


def test_worker_function_options_keep_main_workers_warm(worker_app):
    options = worker_app.worker_function_options(modal_environment="main")

    assert options["min_containers"] == 3
    assert options["buffer_containers"] == 2
    assert options["scaledown_window"] == 600


def test_worker_function_options_do_not_keep_staging_workers_warm():
    from policyengine_household_api.modal_release.worker_app import (
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
    from policyengine_household_api.modal_release.worker_app import (
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


def test_household_worker_exposes_post_snapshot_reset_hook(worker_app):
    """The class must declare a post-restore hook so network state
    captured in the memory snapshot (SQLAlchemy pool, Cloud SQL
    Connector) gets reset on every container start. Modal preserves
    Python object state but not live TCP sockets across snapshots."""
    worker_cls = worker_app.HouseholdWorker
    assert hasattr(worker_cls, "reset_post_snapshot_state")


def test_worker_concurrency_options_set_max_inputs(worker_app):
    """Each container processes up to 5 requests in parallel. Keeping this
    consistent across environments ensures staging behavior mirrors
    production so concurrency-related issues surface in staging tests."""
    assert worker_app.worker_concurrency_options()["max_inputs"] == 5


def test_worker_concurrency_options_set_target_inputs(worker_app):
    """`target_inputs=4` keeps the autoscaler aiming for 80% steady-state
    utilisation, so each container retains a free slot to absorb a
    single-request spike without waiting on a cold start."""
    assert worker_app.worker_concurrency_options()["target_inputs"] == 4


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
