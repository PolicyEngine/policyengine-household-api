import subprocess
import sys

import yaml


def test_apply_scaling_controls_sets_launch_stage_and_target(tmp_path):
    input_yaml = tmp_path / "service.yaml"
    output_yaml = tmp_path / "patched.yaml"
    input_yaml.write_text(
        yaml.safe_dump(
            {
                "apiVersion": "serving.knative.dev/v1",
                "kind": "Service",
                "metadata": {
                    "name": "household-api-worker",
                    "annotations": {"existing": "metadata"},
                },
                "spec": {
                    "template": {
                        "metadata": {
                            "annotations": {"existing": "template"},
                        },
                        "spec": {"containers": [{"image": "image"}]},
                    }
                },
            }
        )
    )

    result = subprocess.run(
        [
            sys.executable,
            ".github/scripts/cloud_run_apply_scaling_controls.py",
            "--input-yaml",
            str(input_yaml),
            "--output-yaml",
            str(output_yaml),
            "--scaling-concurrency-target",
            "0.3",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    service = yaml.safe_load(output_yaml.read_text())
    assert (
        service["metadata"]["annotations"]["run.googleapis.com/launch-stage"]
        == "BETA"
    )
    assert (
        service["spec"]["template"]["metadata"]["annotations"][
            "run.googleapis.com/scaling-concurrency-target"
        ]
        == "0.3"
    )
    assert service["metadata"]["annotations"]["existing"] == "metadata"
    assert (
        service["spec"]["template"]["metadata"]["annotations"]["existing"]
        == "template"
    )


def test_apply_scaling_controls_rejects_invalid_target(tmp_path):
    service_yaml = tmp_path / "service.yaml"
    output_yaml = tmp_path / "patched.yaml"
    service_yaml.write_text("metadata: {}\nspec: {}\n")

    result = subprocess.run(
        [
            sys.executable,
            ".github/scripts/cloud_run_apply_scaling_controls.py",
            "--input-yaml",
            str(service_yaml),
            "--output-yaml",
            str(output_yaml),
            "--scaling-concurrency-target",
            "1.5",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "must be greater than 0 and at most 1" in result.stderr
