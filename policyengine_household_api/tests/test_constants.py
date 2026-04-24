from importlib.metadata import PackageNotFoundError
from pathlib import Path

from policyengine_household_api import constants


def test_get_repo_version_prefers_local_pyproject(monkeypatch, tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nversion = "1.2.3"\n')

    def fake_version(package_name):
        assert package_name == "policyengine-household-api"
        return "9.9.9"

    monkeypatch.setattr(constants, "version", fake_version)
    monkeypatch.setattr(constants, "REPO", Path(tmp_path))

    assert constants.get_repo_version() == "1.2.3"


def test_get_repo_version_falls_back_to_installed_metadata(
    monkeypatch, tmp_path
):
    def fake_version(_package_name):
        return "9.9.9"

    monkeypatch.setattr(constants, "version", fake_version)
    monkeypatch.setattr(constants, "REPO", Path(tmp_path))

    assert constants.get_repo_version() == "9.9.9"


def test_get_repo_version_uses_default_without_metadata_or_pyproject(
    monkeypatch,
    tmp_path,
):
    def fake_version(_package_name):
        raise PackageNotFoundError

    monkeypatch.setattr(constants, "version", fake_version)
    monkeypatch.setattr(constants, "REPO", Path(tmp_path))

    assert constants.get_repo_version() == "0.0.0"
