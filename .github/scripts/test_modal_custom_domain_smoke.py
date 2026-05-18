import os
from pathlib import Path
import subprocess


SCRIPT = ".github/scripts/modal-custom-domain-smoke.sh"


def test_modal_custom_domain_smoke_passes_when_versions_match(tmp_path):
    env = _smoke_env(
        tmp_path,
        gateway_versions='{"current":"1.691.1","frontier":"1.691.1"}',
        custom_versions='{"current":"1.691.1","frontier":"1.691.1"}',
    )

    result = subprocess.run(
        ["bash", SCRIPT],
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert (
        "Custom domain points at the deployed Modal gateway." in result.stdout
    )


def test_modal_custom_domain_smoke_fails_when_custom_domain_is_not_gateway(
    tmp_path,
):
    env = _smoke_env(
        tmp_path,
        gateway_versions='{"current":"1.691.1","frontier":"1.691.1"}',
        custom_versions="OK",
    )

    result = subprocess.run(
        ["bash", SCRIPT],
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 1
    assert "Custom domain /versions/us did not return JSON" in result.stderr


def test_modal_custom_domain_smoke_fails_when_versions_differ(tmp_path):
    env = _smoke_env(
        tmp_path,
        gateway_versions='{"current":"1.691.1","frontier":"1.691.1"}',
        custom_versions='{"current":"1.690.0","frontier":"1.691.1"}',
    )

    result = subprocess.run(
        ["bash", SCRIPT],
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 1
    assert "does not match the generated Modal gateway" in result.stderr


def test_modal_custom_domain_smoke_skips_non_main_environments(tmp_path):
    curl_log = tmp_path / "curl.log"
    env = _smoke_env(
        tmp_path,
        gateway_versions='{"current":"1.691.1"}',
        custom_versions='{"current":"1.691.1"}',
    )
    env["MODAL_ENVIRONMENT"] = "staging"
    env["CURL_LOG"] = str(curl_log)

    result = subprocess.run(
        ["bash", SCRIPT],
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 0
    assert "Skipping custom-domain smoke check" in result.stdout
    assert not curl_log.exists()


def _smoke_env(
    tmp_path: Path,
    *,
    gateway_versions: str,
    custom_versions: str,
) -> dict[str, str]:
    get_url_script = tmp_path / "modal-get-url.sh"
    get_url_script.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "echo https://generated-modal.example\n"
    )
    get_url_script.chmod(0o755)

    fake_curl = tmp_path / "curl"
    fake_curl.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
url="${@: -1}"
if [ -n "${CURL_LOG:-}" ]; then
  printf '%s\\n' "${url}" >> "${CURL_LOG}"
fi

case "${url}" in
  https://generated-modal.example/liveness_check|https://custom-domain.example/liveness_check)
    echo OK
    ;;
  https://generated-modal.example/versions/us)
    printf '%s\\n' "${GATEWAY_VERSIONS}"
    ;;
  https://custom-domain.example/versions/us)
    printf '%s\\n' "${CUSTOM_VERSIONS}"
    ;;
  *)
    echo "Unexpected URL: ${url}" >&2
    exit 22
    ;;
esac
"""
    )
    fake_curl.chmod(0o755)

    return {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "MODAL_ENVIRONMENT": "main",
        "MODAL_GET_URL_SCRIPT": str(get_url_script),
        "HOUSEHOLD_MODAL_GATEWAY_CUSTOM_DOMAIN_URL": (
            "https://custom-domain.example"
        ),
        "GATEWAY_VERSIONS": gateway_versions,
        "CUSTOM_VERSIONS": custom_versions,
    }
