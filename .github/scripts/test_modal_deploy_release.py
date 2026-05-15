import os
import subprocess


def test_modal_deploy_release_requires_explicit_modal_environment():
    env = {
        **os.environ,
        "USER_ANALYTICS_DB_USERNAME": "user",
        "USER_ANALYTICS_DB_PASSWORD": "password",
        "USER_ANALYTICS_DB_CONNECTION_NAME": "project:region:instance",
    }
    env.pop("MODAL_ENVIRONMENT", None)

    result = subprocess.run(
        [
            "bash",
            ".github/scripts/modal-deploy-release.sh",
            '{"new_app_target":"none","promote_existing_frontier":false,"cleanup_target":"none"}',
        ],
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 1
    assert "MODAL_ENVIRONMENT" in result.stdout
