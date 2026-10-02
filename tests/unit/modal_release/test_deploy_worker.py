from contextlib import nullcontext
import importlib

from policyengine_household_modal.worker_deployment import (
    WorkerDeployment,
    WorkerResourceProfile,
)


def test_deploy_worker_passes_typed_configuration_to_modal(monkeypatch):
    deploy_worker_module = importlib.import_module(
        "policyengine_household_modal.deploy_worker"
    )
    deployment = WorkerDeployment(
        app_name="worker",
        modal_environment="testing",
        package_versions={"us": "2.18.0"},
        resource_profile=WorkerResourceProfile.FRONTIER,
    )
    calls = []

    class FakeApp:
        def deploy(self, *, name, environment_name):
            calls.append((name, environment_name))

    monkeypatch.setattr(
        deploy_worker_module,
        "create_worker_app",
        lambda received: FakeApp() if received == deployment else None,
    )
    monkeypatch.setattr(
        deploy_worker_module.modal,
        "enable_output",
        nullcontext,
    )

    deploy_worker_module.deploy_worker(deployment)

    assert calls == [("worker", "testing")]
