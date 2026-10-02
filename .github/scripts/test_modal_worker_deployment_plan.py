import pytest

from modal_worker_deployment_plan import build_worker_deployment_plan
from policyengine_household_common.release_config import (
    CleanupTarget,
    ModalReleaseConfig,
    NewAppTarget,
)
from policyengine_household_modal.worker_deployment import (
    WorkerResourceProfile,
)


CURRENT = {
    "app_name": "current-app",
    "package_versions": {"us": "1.690.0"},
    "resource_profile": "current",
}
FRONTIER = {
    "app_name": "frontier-app",
    "package_versions": {"us": "1.691.1"},
    "resource_profile": "frontier",
}
NEW_VERSIONS = {"us": "1.692.0"}


def _config(
    *,
    new_app_target=NewAppTarget.FRONTIER,
    promote_existing_frontier=True,
):
    return ModalReleaseConfig(
        new_app_target=new_app_target,
        promote_existing_frontier=promote_existing_frontier,
        cleanup_target=CleanupTarget.RETIRED,
    )


def _summary(plan):
    return [
        (
            deployment.app_name,
            dict(deployment.package_versions),
            deployment.resource_profile,
        )
        for deployment in plan
    ]


def test_code_deployment_keeps_active_profiles():
    plan = build_worker_deployment_plan(
        [CURRENT, FRONTIER],
        deploy_mode="code",
        modal_environment="main",
    )

    assert _summary(plan) == [
        ("current-app", {"us": "1.690.0"}, WorkerResourceProfile.CURRENT),
        (
            "frontier-app",
            {"us": "1.691.1"},
            WorkerResourceProfile.FRONTIER,
        ),
    ]


def test_release_promotes_frontier_and_deploys_new_frontier():
    plan = build_worker_deployment_plan(
        [CURRENT, FRONTIER],
        deploy_mode="release",
        modal_environment="main",
        config=_config(),
        new_app_name="new-app",
        new_package_versions=NEW_VERSIONS,
    )

    assert _summary(plan) == [
        (
            "frontier-app",
            {"us": "1.691.1"},
            WorkerResourceProfile.CURRENT,
        ),
        (
            "new-app",
            NEW_VERSIONS,
            WorkerResourceProfile.FRONTIER,
        ),
    ]


def test_release_consolidates_same_app_name_at_current_profile():
    same_app = {
        "app_name": "new-app",
        "package_versions": NEW_VERSIONS,
        "resource_profile": "frontier",
    }

    plan = build_worker_deployment_plan(
        [CURRENT, same_app],
        deploy_mode="release",
        modal_environment="main",
        config=_config(),
        new_app_name="new-app",
        new_package_versions=NEW_VERSIONS,
    )

    assert _summary(plan) == [
        ("new-app", NEW_VERSIONS, WorkerResourceProfile.CURRENT)
    ]


def test_release_does_not_reduce_app_serving_current_traffic():
    same_current = {
        "app_name": "new-app",
        "package_versions": NEW_VERSIONS,
        "resource_profile": "current",
    }

    plan = build_worker_deployment_plan(
        [same_current, FRONTIER],
        deploy_mode="release",
        modal_environment="main",
        config=_config(promote_existing_frontier=False),
        new_app_name="new-app",
        new_package_versions=NEW_VERSIONS,
    )

    assert _summary(plan) == [
        ("new-app", NEW_VERSIONS, WorkerResourceProfile.CURRENT)
    ]


def test_release_uses_current_profile_for_both_channels():
    plan = build_worker_deployment_plan(
        [],
        deploy_mode="release",
        modal_environment="main",
        config=_config(
            new_app_target=NewAppTarget.BOTH,
            promote_existing_frontier=False,
        ),
        new_app_name="new-app",
        new_package_versions=NEW_VERSIONS,
    )

    assert _summary(plan) == [
        ("new-app", NEW_VERSIONS, WorkerResourceProfile.CURRENT)
    ]


def test_release_rejects_same_app_name_with_conflicting_versions():
    same_app = {
        "app_name": "new-app",
        "package_versions": {"us": "1.691.1"},
        "resource_profile": "frontier",
    }

    with pytest.raises(ValueError, match="conflicting package versions"):
        build_worker_deployment_plan(
            [same_app],
            deploy_mode="release",
            modal_environment="main",
            config=_config(),
            new_app_name="new-app",
            new_package_versions=NEW_VERSIONS,
        )
