import os
from pathlib import Path
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


def test_modal_deploy_release_code_mode_deploys_manifest_apps_only(tmp_path):
    log_path = tmp_path / "uv.log"
    env = _deploy_env(tmp_path, log_path)
    active_apps_script = tmp_path / "modal_active_worker_apps.py"
    active_apps_script.write_text("# fake active apps script\n")
    env["MODAL_ACTIVE_WORKER_APPS_SCRIPT"] = str(active_apps_script)
    _write_fake_uv(
        tmp_path,
        log_path,
        active_apps_tsv=(
            'current-app\t{"uk":"2.31.0","us":"1.690.0"}\n'
            'frontier-app\t{"uk":"2.31.0","us":"1.691.1"}\n'
        ),
    )

    result = subprocess.run(
        [
            "bash",
            ".github/scripts/modal-deploy-release.sh",
            "{}",
            "code",
        ],
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    log = log_path.read_text()
    assert "DEPLOY_APP=current-app" in log
    assert 'VERSIONS={"uk":"2.31.0","us":"1.690.0"}' in log
    assert "DEPLOY_APP=frontier-app" in log
    assert 'VERSIONS={"uk":"2.31.0","us":"1.691.1"}' in log
    assert (
        "-m policyengine_household_api.modal_release.update_manifest"
        not in log
    )
    assert "cleanup-called" not in log


def test_modal_deploy_release_release_mode_updates_manifest_and_cleans(
    tmp_path,
):
    log_path = tmp_path / "uv.log"
    env = _deploy_env(tmp_path, log_path)
    _write_fake_uv(tmp_path, log_path, active_apps_tsv="")

    result = subprocess.run(
        [
            "bash",
            ".github/scripts/modal-deploy-release.sh",
            (
                '{"new_app_target":"frontier",'
                '"promote_existing_frontier":true,'
                '"cleanup_target":"retired"}'
            ),
            "release",
        ],
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    log = log_path.read_text()
    assert "DEPLOY_APP=release-app" in log
    assert "-m policyengine_household_api.modal_release.update_manifest" in log
    assert "--source-commit" not in log
    assert "cleanup-called" in log


def _deploy_env(tmp_path: Path, log_path: Path) -> dict[str, str]:
    sync_script = tmp_path / "sync-secrets.sh"
    sync_script.write_text("#!/usr/bin/env bash\nexit 0\n")
    sync_script.chmod(0o755)

    cleanup_script = tmp_path / "cleanup.sh"
    cleanup_script.write_text(
        f"#!/usr/bin/env bash\necho cleanup-called >> {log_path}\n"
    )
    cleanup_script.chmod(0o755)

    get_url_script = tmp_path / "get-url.sh"
    get_url_script.write_text(
        "#!/usr/bin/env bash\necho http://example.test\n"
    )
    get_url_script.chmod(0o755)

    fake_curl = tmp_path / "curl"
    fake_curl.write_text("#!/usr/bin/env bash\nexit 0\n")
    fake_curl.chmod(0o755)

    return {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "UV_LOG": str(log_path),
        "MODAL_ENVIRONMENT": "testing",
        "USER_ANALYTICS_DB_USERNAME": "user",
        "USER_ANALYTICS_DB_PASSWORD": "password",
        "USER_ANALYTICS_DB_CONNECTION_NAME": "project:region:instance",
        "MODAL_SYNC_SECRETS_SCRIPT": str(sync_script),
        "MODAL_CLEANUP_APPS_SCRIPT": str(cleanup_script),
        "MODAL_GET_URL_SCRIPT": str(get_url_script),
    }


def _write_fake_uv(
    tmp_path: Path,
    log_path: Path,
    *,
    active_apps_tsv: str,
) -> None:
    uv = tmp_path / "uv"
    uv.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
echo "$*" >> "${{UV_LOG}}"

if [[ "$*" == *"policyengine_household_api.modal_release.analytics_revision"* ]]; then
  echo "20260512_0003"
  exit 0
fi

if [[ "$*" == *"modal_extract_versions.py"* ]]; then
  while [[ "$#" -gt 0 ]]; do
    if [[ "$1" == "--github-output" ]]; then
      shift
      printf 'worker_app_name=release-app\\n' > "$1"
      exit 0
    fi
    shift
  done
fi

if [[ "$*" == *"modal_active_worker_apps.py"* ]]; then
  while [[ "$#" -gt 0 ]]; do
    if [[ "$1" == "--output-tsv" ]]; then
      shift
      cat > "$1" <<'EOF'
{active_apps_tsv}EOF
      exit 0
    fi
    shift
  done
fi

if [[ "$*" == *"modal deploy"* && "$*" == *"worker_app"* ]]; then
  echo "DEPLOY_APP=${{HOUSEHOLD_MODAL_WORKER_APP_NAME:-}}" >> "{log_path}"
  echo "VERSIONS=${{HOUSEHOLD_MODAL_PACKAGE_VERSIONS_JSON:-}}" >> "{log_path}"
  exit 0
fi

exit 0
"""
    )
    uv.chmod(0o755)
