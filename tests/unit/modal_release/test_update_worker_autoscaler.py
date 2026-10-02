import pytest

from policyengine_household_modal import update_worker_autoscaler as updater


@pytest.mark.parametrize(
    ("profile", "expected"),
    [
        (
            "current",
            {
                "min_containers": 3,
                "buffer_containers": 2,
                "scaledown_window": 600,
            },
        ),
        (
            "frontier",
            {
                "min_containers": 1,
                "buffer_containers": 1,
                "scaledown_window": 300,
            },
        ),
    ],
)
def test_update_worker_autoscaler_applies_profile(
    monkeypatch,
    profile,
    expected,
):
    calls = []

    class FakeWorker:
        def update_autoscaler(self, **options):
            calls.append(options)

    class FakeCls:
        def __call__(self):
            return FakeWorker()

    monkeypatch.setattr(
        updater.modal.Cls,
        "from_name",
        lambda app_name, class_name, environment_name: FakeCls(),
    )

    updater.update_worker_autoscaler(
        app_name="worker",
        modal_environment="main",
        resource_profile=profile,
    )

    assert calls == [expected]
