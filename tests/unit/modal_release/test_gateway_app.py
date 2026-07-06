import os
import subprocess
from pathlib import Path

from policyengine_household_modal.gateway_app import (
    GATEWAY_APP_NAME,
    GATEWAY_CUSTOM_DOMAIN,
    GATEWAY_WEB_ENDPOINT_LABEL,
    gateway_custom_domains,
    gateway_wsgi_app_options,
)


def test_gateway_web_endpoint_label_is_short_and_stable():
    assert GATEWAY_WEB_ENDPOINT_LABEL == "household-api-gateway"


def test_gateway_wsgi_app_options_registers_production_custom_domain():
    assert gateway_wsgi_app_options(modal_environment="main") == {
        "label": GATEWAY_WEB_ENDPOINT_LABEL,
        "custom_domains": (GATEWAY_CUSTOM_DOMAIN,),
    }


def test_gateway_wsgi_app_options_do_not_register_staging_custom_domains():
    assert gateway_wsgi_app_options(modal_environment="staging") == {
        "label": GATEWAY_WEB_ENDPOINT_LABEL
    }


def test_gateway_custom_domain_override_supports_multiple_domains():
    assert gateway_custom_domains(
        modal_environment="staging",
        custom_domains=" api.example.org, secondary.example.org ",
    ) == ("api.example.org", "secondary.example.org")


def test_gateway_custom_domain_override_can_disable_domains():
    assert gateway_wsgi_app_options(
        modal_environment="main",
        custom_domains="",
    ) == {"label": GATEWAY_WEB_ENDPOINT_LABEL}


def test_gateway_web_endpoint_label_fits_modal_hostname_limit():
    for environment in ("main", "staging", "testing"):
        source = _modal_source(environment)
        subdomain = f"{source}--{GATEWAY_WEB_ENDPOINT_LABEL}"

        assert len(subdomain) <= 63


def test_modal_get_url_uses_deployed_modal_function_url(tmp_path):
    script = Path(".github/scripts/modal-get-url.sh")
    fake_uv = tmp_path / "uv"
    args_file = tmp_path / "uv-args.txt"
    fake_uv.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                'printf "%s %s %s\\n" "$4" "$5" "$6" > "$UV_ARGS_FILE"',
                "cat >/dev/null",
                "echo https://policyengine-testing--household-api-gateway.modal.run",
            ]
        )
        + "\n"
    )
    fake_uv.chmod(0o755)

    env = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "MODAL_ENVIRONMENT": "testing",
        "HOUSEHOLD_MODAL_GATEWAY_APP_NAME": GATEWAY_APP_NAME,
        "UV_ARGS_FILE": str(args_file),
    }

    result = subprocess.run(
        ["bash", str(script)],
        check=True,
        capture_output=True,
        env=env,
        text=True,
    )

    assert (
        result.stdout.strip()
        == "https://policyengine-testing--household-api-gateway.modal.run"
    )
    assert args_file.read_text() == f"{GATEWAY_APP_NAME} web_app testing\n"


def _modal_source(environment: str) -> str:
    if environment == "main":
        return "policyengine"
    return f"policyengine-{environment}"
