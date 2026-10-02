import pytest

from policyengine_household_modal.worker_deployment import (
    WorkerDeployment,
    WorkerResourceProfile,
    parse_package_versions_json,
)


def test_worker_deployment_copies_and_freezes_package_versions():
    package_versions = {"us": "2.18.0"}
    deployment = WorkerDeployment(
        app_name="worker",
        modal_environment="main",
        package_versions=package_versions,
        resource_profile=WorkerResourceProfile.CURRENT,
    )

    package_versions["us"] = "3.0.0"

    assert dict(deployment.package_versions) == {"us": "2.18.0"}
    with pytest.raises(TypeError):
        deployment.package_versions["uk"] = "2.88.18"


@pytest.mark.parametrize(
    ("field", "value", "error_type", "message"),
    [
        ("app_name", "", ValueError, "app name"),
        ("modal_environment", "", ValueError, "environment"),
        (
            "package_versions",
            {"us": ""},
            ValueError,
            "Package versions",
        ),
        (
            "package_versions",
            ["us"],
            TypeError,
            "must be a mapping",
        ),
        (
            "resource_profile",
            "current",
            TypeError,
            "WorkerResourceProfile",
        ),
    ],
)
def test_worker_deployment_rejects_invalid_configuration(
    field,
    value,
    error_type,
    message,
):
    values = {
        "app_name": "worker",
        "modal_environment": "main",
        "package_versions": {"us": "2.18.0"},
        "resource_profile": WorkerResourceProfile.CURRENT,
    }
    values[field] = value

    with pytest.raises(error_type, match=message):
        WorkerDeployment(**values)


def test_parse_package_versions_json_returns_validated_mapping():
    assert parse_package_versions_json('{"uk":"2.88.18","us":"2.18.0"}') == {
        "uk": "2.88.18",
        "us": "2.18.0",
    }


@pytest.mark.parametrize(
    "raw_value",
    [
        "not-json",
        '["us"]',
        '{"": "2.18.0"}',
        '{"us": ""}',
        '{"us": 2}',
    ],
)
def test_parse_package_versions_json_rejects_invalid_values(raw_value):
    with pytest.raises(ValueError, match="Package versions"):
        parse_package_versions_json(raw_value)
