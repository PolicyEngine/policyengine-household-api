import os
from pathlib import Path
import subprocess

import pytest


def _base_env(tmp_path: Path, output_path: Path) -> dict:
    return {
        # Strip inherited observability vars so the assertions below see
        # exactly the values this test sets, not developer-shell state.
        **{
            key: value
            for key, value in os.environ.items()
            if not key.startswith("OBSERVABILITY_")
        },
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "UV_BIN": str(tmp_path / "uv"),
        "DOCKER_BIN": str(tmp_path / "docker"),
        "GCLOUD_BIN": str(tmp_path / "gcloud"),
        "GITHUB_OUTPUT": str(output_path),
        "GITHUB_SHA": "abc123",
        "MODAL_ENVIRONMENT": "staging",
        "GOOGLE_CLOUD_PROJECT": "policyengine-test",
        "ANALYTICS__ENABLED": "true",
        "HOUSEHOLD_CLOUD_RUN_ANALYTICS_WRITER_SERVICE_ACCOUNT": (
            "household-api-analytics-writer@policyengine-test.iam.gserviceaccount.com"
        ),
        "USER_ANALYTICS_DB_CONNECTION_NAME": "project:region:db",
        "USER_ANALYTICS_DB_USERNAME": "analytics-user",
        "USER_ANALYTICS_DB_PASSWORD": "analytics@password,with,comma",
        "OBSERVABILITY_ENABLED": "true",
        "OBSERVABILITY_LOG_RAW_IP": "false",
        "OBSERVABILITY_REQUEST_LOGS_ENABLED": "true",
    }


def test_cloud_run_deploy_analytics_deploys_writer_with_startup_probe(
    tmp_path,
):
    log_path = tmp_path / "commands.log"
    output_path = tmp_path / "github-output.txt"
    _write_fake_uv(tmp_path, log_path)
    _write_fake_docker(tmp_path, log_path)
    _write_fake_gcloud(tmp_path, log_path)
    env = _base_env(tmp_path, output_path)

    result = subprocess.run(
        ["bash", ".github/scripts/cloud-run-deploy-analytics.sh"],
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    log = log_path.read_text()
    assert (
        "docker build --file gcp/cloud_run/analytics_writer.Dockerfile" in log
    )
    assert "docker push" in log
    assert "gcloud run deploy household-api-staging-analytics-writer" in log
    assert "--no-allow-unauthenticated" in log
    assert "--timeout 300" in log
    assert (
        "--service-account "
        "household-api-analytics-writer@policyengine-test.iam.gserviceaccount.com"
        in log
    )
    assert "APP__ENVIRONMENT: |-" in log
    assert "  staging" in log
    assert "OBSERVABILITY_PLATFORM: |-" in log
    # GOOGLE_CLOUD_PROJECT is the runtime project here; the log sink must
    # fall back to the fixed dedicated project instead of drifting to it.
    assert (
        "OBSERVABILITY_GOOGLE_CLOUD_PROJECT: |-\n"
        "  policyengine-observability\n"
    ) in log
    # Unset observability knobs must be omitted so the package's clamped
    # defaults govern at runtime.
    assert "OBSERVABILITY_GOOGLE_CLOUD_LOG_NAME" not in log
    assert "WEB_TIMEOUT: |-" in log
    assert "USER_ANALYTICS_DB_CONNECTION_NAME: |-" in log
    assert (
        "--set-secrets=USER_ANALYTICS_DB_PASSWORD="
        "household-api-staging-USER_ANALYTICS_DB_PASSWORD:latest" in log
    )
    assert "analytics@password,with,comma" not in log
    assert "cloud_run_apply_startup_probe.py" in log
    assert (
        "--path /liveness_check --period-seconds 2 "
        "--timeout-seconds 2 --failure-threshold 30" in log
    )
    assert "gcloud run services replace" in log
    assert (
        "analytics_writer_url="
        "https://household-api-staging-analytics-writer.run.app"
        in output_path.read_text()
    )


def test_cloud_run_deploy_analytics_adds_password_version_when_none_stored(
    tmp_path,
):
    log_path = tmp_path / "commands.log"
    output_path = tmp_path / "github-output.txt"
    _write_fake_uv(tmp_path, log_path)
    _write_fake_docker(tmp_path, log_path)
    _write_fake_gcloud(tmp_path, log_path)
    env = _base_env(tmp_path, output_path)

    result = subprocess.run(
        ["bash", ".github/scripts/cloud-run-deploy-analytics.sh"],
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    log = log_path.read_text()
    assert (
        "gcloud secrets versions access latest "
        "--secret household-api-staging-USER_ANALYTICS_DB_PASSWORD "
        "--project policyengine-test" in log
    )
    assert log.count("gcloud secrets versions add") == 1
    assert (
        "gcloud secrets versions add "
        "household-api-staging-USER_ANALYTICS_DB_PASSWORD "
        "--project policyengine-test --data-file " in log
    )
    # The secret exists but its latest version cannot be read, so the deploy
    # adds a version and says so as a workflow warning.
    assert (
        "::warning::Secret Manager secret "
        "household-api-staging-USER_ANALYTICS_DB_PASSWORD: could not read "
        "the latest version" in result.stdout
    )
    assert "NOT_FOUND" not in result.stdout
    assert "NOT_FOUND" not in result.stderr
    assert "analytics@password,with,comma" not in log
    assert "analytics@password,with,comma" not in result.stdout


def test_cloud_run_deploy_analytics_keeps_password_version_when_unchanged(
    tmp_path,
):
    log_path = tmp_path / "commands.log"
    output_path = tmp_path / "github-output.txt"
    _write_fake_uv(tmp_path, log_path)
    _write_fake_docker(tmp_path, log_path)
    _write_fake_gcloud(
        tmp_path,
        log_path,
        {
            "household-api-staging-USER_ANALYTICS_DB_PASSWORD": (
                "analytics@password,with,comma"
            )
        },
    )
    env = _base_env(tmp_path, output_path)

    result = subprocess.run(
        ["bash", ".github/scripts/cloud-run-deploy-analytics.sh"],
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    log = log_path.read_text()
    assert "gcloud secrets versions add" not in log
    assert (
        "household-api-staging-USER_ANALYTICS_DB_PASSWORD: latest version "
        "already holds this value; not adding a version." in result.stdout
    )
    assert (
        "--set-secrets=USER_ANALYTICS_DB_PASSWORD="
        "household-api-staging-USER_ANALYTICS_DB_PASSWORD:latest" in log
    )
    assert "analytics@password,with,comma" not in log
    assert "analytics@password,with,comma" not in result.stdout
    assert "analytics@password,with,comma" not in result.stderr


@pytest.mark.parametrize(
    ("stored_password", "deploy_password", "expect_new_version"),
    [
        pytest.param(
            b"analytics-password",
            "analytics-password\n",
            True,
            id="deploy-value-adds-trailing-newline",
        ),
        pytest.param(
            b"analytics-password\n",
            "analytics-password",
            True,
            id="stored-value-has-trailing-newline",
        ),
        pytest.param(
            b"analytics-password ",
            "analytics-password",
            True,
            id="stored-value-has-trailing-space",
        ),
        pytest.param(
            b"analytics-password\n",
            "analytics-password\n",
            False,
            id="both-have-trailing-newline",
        ),
        pytest.param(
            "pässwörd-ünïcode".encode(),
            "pässwörd-ünïcode",
            False,
            id="same-non-ascii-value",
        ),
    ],
)
def test_cloud_run_deploy_analytics_compares_password_bytes_exactly(
    tmp_path, stored_password, deploy_password, expect_new_version
):
    # A comparison through `$(...)` would strip trailing newlines and keep a
    # stale version; only an exact byte match may skip adding a version.
    log_path = tmp_path / "commands.log"
    output_path = tmp_path / "github-output.txt"
    _write_fake_uv(tmp_path, log_path)
    _write_fake_docker(tmp_path, log_path)
    _write_fake_gcloud(
        tmp_path,
        log_path,
        {"household-api-staging-USER_ANALYTICS_DB_PASSWORD": stored_password},
    )
    env = {
        **_base_env(tmp_path, output_path),
        "USER_ANALYTICS_DB_PASSWORD": deploy_password,
    }

    result = subprocess.run(
        ["bash", ".github/scripts/cloud-run-deploy-analytics.sh"],
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    log = log_path.read_text()
    added_versions = log.count(
        "gcloud secrets versions add "
        "household-api-staging-USER_ANALYTICS_DB_PASSWORD"
    )
    if expect_new_version:
        assert added_versions == 1
        assert (
            "household-api-staging-USER_ANALYTICS_DB_PASSWORD: deploy value "
            "differs from the latest version; adding a version."
            in result.stdout
        )
    else:
        assert added_versions == 0
        assert (
            "household-api-staging-USER_ANALYTICS_DB_PASSWORD: latest version "
            "already holds this value; not adding a version." in result.stdout
        )
    assert "::warning::" not in result.stdout
    assert "analytics-password" not in result.stdout
    assert "analytics-password" not in result.stderr


def test_cloud_run_deploy_analytics_adds_password_version_when_read_fails(
    tmp_path,
):
    # gcloud prints the matching value but then exits non-zero, as for any
    # failed read. A match must require a successful read, so the deploy
    # adds a version, warns, and keeps gcloud's error text out of the log.
    log_path = tmp_path / "commands.log"
    output_path = tmp_path / "github-output.txt"
    _write_fake_uv(tmp_path, log_path)
    _write_fake_docker(tmp_path, log_path)
    _write_fake_gcloud(
        tmp_path,
        log_path,
        {
            "household-api-staging-USER_ANALYTICS_DB_PASSWORD": (
                "analytics@password,with,comma"
            )
        },
        unreadable_secret_names={
            "household-api-staging-USER_ANALYTICS_DB_PASSWORD"
        },
    )
    env = _base_env(tmp_path, output_path)

    result = subprocess.run(
        ["bash", ".github/scripts/cloud-run-deploy-analytics.sh"],
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    log = log_path.read_text()
    assert (
        log.count(
            "gcloud secrets versions add "
            "household-api-staging-USER_ANALYTICS_DB_PASSWORD"
        )
        == 1
    )
    assert (
        "::warning::Secret Manager secret "
        "household-api-staging-USER_ANALYTICS_DB_PASSWORD: could not read "
        "the latest version" in result.stdout
    )
    assert "already holds this value" not in result.stdout
    assert "PERMISSION_DENIED" not in result.stdout
    assert "PERMISSION_DENIED" not in result.stderr
    assert "analytics@password,with,comma" not in result.stdout
    assert "analytics@password,with,comma" not in result.stderr


def test_cloud_run_deploy_analytics_creates_password_secret_without_reading(
    tmp_path,
):
    log_path = tmp_path / "commands.log"
    output_path = tmp_path / "github-output.txt"
    _write_fake_uv(tmp_path, log_path)
    _write_fake_docker(tmp_path, log_path)
    _write_fake_gcloud(
        tmp_path,
        log_path,
        missing_secret_names={
            "household-api-staging-USER_ANALYTICS_DB_PASSWORD"
        },
    )
    env = _base_env(tmp_path, output_path)

    result = subprocess.run(
        ["bash", ".github/scripts/cloud-run-deploy-analytics.sh"],
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    log = log_path.read_text()
    assert (
        "gcloud secrets create "
        "household-api-staging-USER_ANALYTICS_DB_PASSWORD" in log
    )
    # A new secret has no versions, so there is nothing to read first.
    assert "gcloud secrets versions access" not in log
    assert (
        log.count(
            "gcloud secrets versions add "
            "household-api-staging-USER_ANALYTICS_DB_PASSWORD"
        )
        == 1
    )
    assert (
        "household-api-staging-USER_ANALYTICS_DB_PASSWORD: created the "
        "secret; adding its first version." in result.stdout
    )
    assert "::warning::" not in result.stdout
    assert (
        "--set-secrets=USER_ANALYTICS_DB_PASSWORD="
        "household-api-staging-USER_ANALYTICS_DB_PASSWORD:latest" in log
    )


def test_cloud_run_deploy_analytics_skips_when_analytics_disabled(tmp_path):
    log_path = tmp_path / "commands.log"
    output_path = tmp_path / "github-output.txt"
    _write_fake_gcloud(tmp_path, log_path)
    env = _base_env(tmp_path, output_path)
    env["ANALYTICS__ENABLED"] = "false"
    env.pop("HOUSEHOLD_CLOUD_RUN_ANALYTICS_WRITER_SERVICE_ACCOUNT", None)

    result = subprocess.run(
        ["bash", ".github/scripts/cloud-run-deploy-analytics.sh"],
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "skipping Cloud Run analytics writer deploy" in result.stdout
    assert not log_path.exists()
    assert not output_path.exists()


def test_cloud_run_deploy_analytics_requires_writer_service_account(
    tmp_path,
):
    log_path = tmp_path / "commands.log"
    output_path = tmp_path / "github-output.txt"
    _write_fake_gcloud(tmp_path, log_path)
    env = _base_env(tmp_path, output_path)
    env.pop("HOUSEHOLD_CLOUD_RUN_ANALYTICS_WRITER_SERVICE_ACCOUNT", None)

    result = subprocess.run(
        ["bash", ".github/scripts/cloud-run-deploy-analytics.sh"],
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 1
    assert (
        "HOUSEHOLD_CLOUD_RUN_ANALYTICS_WRITER_SERVICE_ACCOUNT" in result.stdout
    )


def _write_fake_uv(tmp_path: Path, log_path: Path) -> None:
    script = tmp_path / "uv"
    script.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
echo "uv $*" >> "{log_path}"
"""
    )
    script.chmod(0o755)


def _write_fake_docker(tmp_path: Path, log_path: Path) -> None:
    script = tmp_path / "docker"
    script.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
echo "docker $*" >> "{log_path}"
"""
    )
    script.chmod(0o755)


def _write_fake_gcloud(
    tmp_path: Path,
    log_path: Path,
    stored_secret_values: dict[str, str | bytes] | None = None,
    unreadable_secret_names: set[str] | None = None,
    missing_secret_names: set[str] | None = None,
) -> None:
    # Fake Secret Manager state, by secret name:
    # - `secrets describe` fails for missing_secret_names, succeeds otherwise.
    # - `secrets versions access latest` prints the stored bytes from
    #   stored_secret_values and exits 0. For unreadable_secret_names it
    #   prints any stored bytes, then fails like a permission error. For any
    #   other secret it fails like a missing version.
    secret_store_dir = tmp_path / "secret-store"
    unreadable_dir = tmp_path / "secret-unreadable"
    missing_dir = tmp_path / "secret-missing"
    for directory in (secret_store_dir, unreadable_dir, missing_dir):
        directory.mkdir(exist_ok=True)
    for secret_name, stored_value in (stored_secret_values or {}).items():
        stored_bytes = (
            stored_value.encode()
            if isinstance(stored_value, str)
            else stored_value
        )
        (secret_store_dir / secret_name).write_bytes(stored_bytes)
    for secret_name in unreadable_secret_names or set():
        (unreadable_dir / secret_name).touch()
    for secret_name in missing_secret_names or set():
        (missing_dir / secret_name).touch()

    script = tmp_path / "gcloud"
    script.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
echo "gcloud $*" >> "{log_path}"

if [[ "${{1:-}}" == secrets && "${{2:-}}" == describe ]]; then
  if [[ -f "{missing_dir}/${{3:-}}" ]]; then
    echo "NOT_FOUND: secret not found" >&2
    exit 1
  fi
  exit 0
fi

if [[ "${{1:-}}" == secrets && "${{2:-}}" == versions && "${{3:-}}" == access ]]; then
  secret_name=""
  previous_arg=""
  for arg in "$@"; do
    if [[ "${{previous_arg}}" == --secret ]]; then
      secret_name="${{arg}}"
    fi
    previous_arg="${{arg}}"
  done
  stored_value_file="{secret_store_dir}/${{secret_name}}"
  if [[ -n "${{secret_name}}" && -f "{unreadable_dir}/${{secret_name}}" ]]; then
    if [[ -f "${{stored_value_file}}" ]]; then
      cat "${{stored_value_file}}"
    fi
    echo "PERMISSION_DENIED: secretmanager.versions.access denied" >&2
    exit 1
  fi
  if [[ -n "${{secret_name}}" && -f "${{stored_value_file}}" ]]; then
    cat "${{stored_value_file}}"
    exit 0
  fi
  echo "NOT_FOUND: secret version not found" >&2
  exit 1
fi

for arg in "$@"; do
  if [[ "${{arg}}" == --env-vars-file=* ]]; then
    echo "env-vars-file ${{arg#--env-vars-file=}}" >> "{log_path}"
    cat "${{arg#--env-vars-file=}}" >> "{log_path}"
  fi
done

if [[ "$*" == artifacts\\ repositories\\ describe* ]]; then
  exit 0
fi

if [[ "$*" == run\\ services\\ describe* ]]; then
  service="$4"
  echo "https://${{service}}.run.app"
  exit 0
fi

exit 0
"""
    )
    script.chmod(0o755)
