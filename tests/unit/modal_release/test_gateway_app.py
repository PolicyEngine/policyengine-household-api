import os
import subprocess
from pathlib import Path

from policyengine_household_api.modal_release.gateway_app import (
    GATEWAY_APP_NAME,
    GATEWAY_WEB_ENDPOINT_LABEL,
)


def test_gateway_web_endpoint_label_matches_app_name():
    assert GATEWAY_WEB_ENDPOINT_LABEL == f"{GATEWAY_APP_NAME}-web-app"


def test_modal_get_url_matches_gateway_web_endpoint_label():
    script = Path(".github/scripts/modal-get-url.sh")
    env = {
        **os.environ,
        "MODAL_WORKSPACE": "policyengine",
        "MODAL_ENVIRONMENT": "staging",
        "HOUSEHOLD_MODAL_GATEWAY_APP_NAME": GATEWAY_APP_NAME,
    }

    result = subprocess.run(
        ["bash", str(script)],
        check=True,
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.stdout.strip() == (
        f"https://policyengine-staging--{GATEWAY_WEB_ENDPOINT_LABEL}.modal.run"
    )


def test_modal_get_url_matches_main_gateway_web_endpoint_label():
    script = Path(".github/scripts/modal-get-url.sh")
    env = {
        **os.environ,
        "MODAL_WORKSPACE": "policyengine",
        "MODAL_ENVIRONMENT": "main",
        "HOUSEHOLD_MODAL_GATEWAY_APP_NAME": GATEWAY_APP_NAME,
    }

    result = subprocess.run(
        ["bash", str(script)],
        check=True,
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.stdout.strip() == (
        f"https://policyengine--{GATEWAY_WEB_ENDPOINT_LABEL}.modal.run"
    )
