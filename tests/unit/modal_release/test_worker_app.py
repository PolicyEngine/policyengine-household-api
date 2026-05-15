import importlib

import pytest


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
