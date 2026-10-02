import json

import modal_extract_versions


def test_modal_extract_versions_emits_package_versions_json(
    monkeypatch,
    tmp_path,
):
    output_path = tmp_path / "github-output"
    package_versions = {"uk": "2.88.18", "us": "2.18.0"}
    monkeypatch.setattr(
        modal_extract_versions,
        "current_package_versions",
        lambda: package_versions,
    )
    monkeypatch.setattr(
        modal_extract_versions,
        "build_app_name",
        lambda versions: "release-app",
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "modal_extract_versions.py",
            "--github-output",
            str(output_path),
        ],
    )

    modal_extract_versions.main()

    output = dict(
        line.split("=", 1) for line in output_path.read_text().splitlines()
    )
    assert output["worker_app_name"] == "release-app"
    assert json.loads(output["package_versions_json"]) == package_versions
