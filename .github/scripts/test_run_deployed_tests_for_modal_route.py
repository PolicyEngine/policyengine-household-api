import os
import subprocess


def test_run_deployed_tests_resolves_and_exports_modal_gateway_url(tmp_path):
    modal_get_url_script = tmp_path / "modal-get-url.sh"
    deployed_tests_script = tmp_path / "run-deployed-tests.sh"
    fake_python = tmp_path / "python"
    env_file = tmp_path / "env.txt"

    modal_get_url_script.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "echo https://policyengine-staging--household-api-gateway.modal.run\n"
    )
    modal_get_url_script.chmod(0o755)

    fake_python.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "echo current\n"
    )
    fake_python.chmod(0o755)

    deployed_tests_script.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "printf '%s\\n' \"$HOUSEHOLD_API_BASE_URL\" > \"$ENV_FILE\"\n"
        "printf '%s\\n' \"$HOUSEHOLD_API_REQUEST_VERSION\" >> \"$ENV_FILE\"\n"
        "printf '%s\\n' \"$HOUSEHOLD_API_EXPECTED_CHANNEL\" >> \"$ENV_FILE\"\n"
        "printf '%s\\n' \"$HOUSEHOLD_API_ROUTE_MODE\" >> \"$ENV_FILE\"\n"
    )
    deployed_tests_script.chmod(0o755)

    env = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "ENV_FILE": str(env_file),
        "HOUSEHOLD_MODAL_GET_URL_SCRIPT": str(modal_get_url_script),
        "HOUSEHOLD_DEPLOYED_TESTS_SCRIPT": str(deployed_tests_script),
    }
    env.pop("HOUSEHOLD_API_BASE_URL", None)

    result = subprocess.run(
        [
            "bash",
            ".github/scripts/run-deployed-tests-for-modal-route.sh",
            "current",
            "channel",
        ],
        check=True,
        capture_output=True,
        env=env,
        text=True,
    )

    assert (
        "Running deployed tests against Modal current via channel routing"
        in result.stdout
    )
    assert env_file.read_text().splitlines() == [
        "https://policyengine-staging--household-api-gateway.modal.run",
        "current",
        "current",
        "channel",
    ]
