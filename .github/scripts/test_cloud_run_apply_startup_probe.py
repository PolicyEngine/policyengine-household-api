import subprocess
import sys

import yaml


def _service_yaml() -> dict:
    return {
        "apiVersion": "serving.knative.dev/v1",
        "kind": "Service",
        "metadata": {"name": "household-api-analytics-writer"},
        "spec": {
            "template": {
                "spec": {"containers": [{"image": "image"}]},
            }
        },
    }


def _run(tmp_path, *extra_args):
    input_yaml = tmp_path / "service.yaml"
    output_yaml = tmp_path / "patched.yaml"
    input_yaml.write_text(yaml.safe_dump(_service_yaml()))
    result = subprocess.run(
        [
            sys.executable,
            ".github/scripts/cloud_run_apply_startup_probe.py",
            "--input-yaml",
            str(input_yaml),
            "--output-yaml",
            str(output_yaml),
            *extra_args,
        ],
        capture_output=True,
        text=True,
    )
    return result, output_yaml


def test_apply_startup_probe_sets_http_probe(tmp_path):
    result, output_yaml = _run(
        tmp_path,
        "--path",
        "/liveness_check",
        "--period-seconds",
        "2",
        "--timeout-seconds",
        "2",
        "--failure-threshold",
        "30",
    )

    assert result.returncode == 0, result.stderr
    patched = yaml.safe_load(output_yaml.read_text())
    container = patched["spec"]["template"]["spec"]["containers"][0]
    assert container["image"] == "image"
    assert container["startupProbe"] == {
        "httpGet": {"path": "/liveness_check"},
        "initialDelaySeconds": 0,
        "periodSeconds": 2,
        "timeoutSeconds": 2,
        "failureThreshold": 30,
    }


def test_apply_startup_probe_overwrites_existing_probe(tmp_path):
    input_yaml = tmp_path / "service.yaml"
    output_yaml = tmp_path / "patched.yaml"
    service = _service_yaml()
    service["spec"]["template"]["spec"]["containers"][0]["startupProbe"] = {
        "tcpSocket": {"port": 8080},
    }
    input_yaml.write_text(yaml.safe_dump(service))

    result = subprocess.run(
        [
            sys.executable,
            ".github/scripts/cloud_run_apply_startup_probe.py",
            "--input-yaml",
            str(input_yaml),
            "--output-yaml",
            str(output_yaml),
            "--period-seconds",
            "5",
            "--timeout-seconds",
            "3",
            "--failure-threshold",
            "60",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    patched = yaml.safe_load(output_yaml.read_text())
    probe = patched["spec"]["template"]["spec"]["containers"][0][
        "startupProbe"
    ]
    assert "tcpSocket" not in probe
    assert probe["httpGet"] == {"path": "/liveness_check"}
    assert probe["periodSeconds"] == 5
    assert probe["timeoutSeconds"] == 3
    assert probe["failureThreshold"] == 60


def test_apply_startup_probe_rejects_non_positive_values(tmp_path):
    result, _ = _run(
        tmp_path,
        "--period-seconds",
        "0",
        "--timeout-seconds",
        "2",
        "--failure-threshold",
        "30",
    )

    assert result.returncode != 0
    assert "--period-seconds must be a positive integer" in result.stderr
