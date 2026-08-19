import os
import subprocess


SCRIPT = ".github/scripts/run-deployed-tests-for-cloud-run-route.sh"


def test_run_deployed_tests_requires_cloud_run_base_url(tmp_path):
    env = {**os.environ}
    env.pop("HOUSEHOLD_API_BASE_URL", None)

    result = subprocess.run(
        ["bash", SCRIPT, "current", "channel"],
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 1
    assert "HOUSEHOLD_API_BASE_URL must be set" in result.stderr


def test_run_deployed_tests_exports_cloud_run_route_context(tmp_path):
    deployed_tests_script = tmp_path / "run-deployed-tests.sh"
    env_file = tmp_path / "env.txt"
    deployed_tests_script.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'printf \'%s\\n\' "$HOUSEHOLD_API_BASE_URL" > "$ENV_FILE"\n'
        'printf \'%s\\n\' "$HOUSEHOLD_API_EXPECTED_CHANNEL" >> "$ENV_FILE"\n'
        'printf \'%s\\n\' "$HOUSEHOLD_API_ROUTE_MODE" >> "$ENV_FILE"\n'
    )
    deployed_tests_script.chmod(0o755)
    env = {
        **os.environ,
        "ENV_FILE": str(env_file),
        "HOUSEHOLD_API_BASE_URL": "https://staging-gateway.run.app",
        "HOUSEHOLD_DEPLOYED_TESTS_SCRIPT": str(deployed_tests_script),
    }

    result = subprocess.run(
        ["bash", SCRIPT, "frontier", "exact"],
        check=True,
        capture_output=True,
        env=env,
        text=True,
    )

    assert (
        "Running deployed tests through Cloud Run for frontier via exact routing"
        in result.stdout
    )
    assert env_file.read_text().splitlines() == [
        "https://staging-gateway.run.app",
        "frontier",
        "exact",
    ]
