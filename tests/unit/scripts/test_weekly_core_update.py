import pytest
import requests


@pytest.mark.parametrize("name", ["policyengine-core", "policyengine_core"])
def test_bumps_core_to_smallest_compatible_release(
    check_updates, weekly_project, pypi_metadata, mock_pypi, name
):
    pypi_metadata["https://pypi.org/pypi/policyengine-us/2.17.2/json"]["info"][
        "requires_dist"
    ] = [f"{name}>=3.32.8"]

    assert check_updates.find_required_core_update(
        weekly_project.read_text(), "2.17.2"
    ) == {"policyengine_core": {"old": "3.30.3", "new": "3.32.8"}}


def test_keeps_compatible_core_without_fetching_releases(
    check_updates, weekly_project, mock_pypi
):
    content = weekly_project.read_text().replace("3.30.3", "3.32.9")

    assert check_updates.find_required_core_update(content, "2.17.2") == {}
    assert mock_pypi.call_count == 1


def test_respects_bounds_and_excludes_unavailable_releases(
    check_updates, weekly_project, pypi_metadata, mock_pypi
):
    pypi_metadata["https://pypi.org/pypi/policyengine-us/2.17.2/json"]["info"][
        "requires_dist"
    ] = ["policyengine-core>=3.32.8,<3.33,!=3.32.9"]
    pypi_metadata["https://pypi.org/pypi/policyengine-core/json"][
        "releases"
    ] = {
        "3.32.8": [{"yanked": True}],
        "3.32.9": [{"yanked": False}],
        "3.32.10rc1": [{"yanked": False}],
        "3.32.10.dev1": [{"yanked": False}],
        "3.32.10": [],
        "3.32.11": [{"yanked": False}],
        "3.33.0": [{"yanked": False}],
    }

    assert (
        check_updates.find_required_core_update(
            weekly_project.read_text(), "2.17.2"
        )["policyengine_core"]["new"]
        == "3.32.11"
    )


@pytest.mark.parametrize(
    "requirements",
    [None, ["pandas>=3"], ['policyengine-core>=4; extra == "dev"']],
)
def test_no_core_update_without_unconditional_requirement(
    check_updates, weekly_project, pypi_metadata, mock_pypi, requirements
):
    pypi_metadata["https://pypi.org/pypi/policyengine-us/2.17.2/json"]["info"][
        "requires_dist"
    ] = requirements

    assert (
        check_updates.find_required_core_update(
            weekly_project.read_text(), "2.17.2"
        )
        == {}
    )
    assert mock_pypi.call_count == 1


def test_fails_when_no_compatible_core_upgrade_exists(
    check_updates, weekly_project, pypi_metadata, mock_pypi
):
    pypi_metadata["https://pypi.org/pypi/policyengine-core/json"][
        "releases"
    ] = {"3.30.3": [{"yanked": False}]}

    with pytest.raises(
        ValueError, match="No stable policyengine-core upgrade"
    ):
        check_updates.find_required_core_update(
            weekly_project.read_text(), "2.17.2"
        )


def test_main_records_both_updates_and_preserves_other_dependencies(
    check_updates, weekly_project, mock_pypi, monkeypatch, tmp_path
):
    monkeypatch.setattr(
        check_updates,
        "get_latest_versions",
        lambda: {"policyengine_us": "2.17.2"},
    )
    monkeypatch.setattr(check_updates, "fetch_changelog", lambda pkg: None)

    assert check_updates.main() == 0

    content = weekly_project.read_text()
    assert '"policyengine_us==2.17.2"' in content
    assert '"policyengine-core==3.32.8"' in content
    assert '"policyengine_uk==2.88.18"' in content
    assert '"flask>=3.1.3"' in content
    summary = (tmp_path / "pr_summary.md").read_text()
    assert "| policyengine_us | 2.9.0 | 2.17.2 |" in summary
    assert "| policyengine_core | 3.30.3 | 3.32.8 |" in summary
    fragment = (
        tmp_path / "changelog.d/policyengine-us-2.17.2.changed.md"
    ).read_text()
    assert "Update PolicyEngine US to 2.17.2." in fragment
    assert "Update PolicyEngine Core to 3.32.8 as required by US." in fragment
    output = (tmp_path / "github-output").read_text()
    assert "has_updates=true" in output
    assert "policyengine_core to 3.32.8" in output


def test_main_does_not_update_core_without_us_update(
    check_updates, weekly_project, mock_pypi, monkeypatch
):
    original = weekly_project.read_text()
    monkeypatch.setattr(
        check_updates,
        "get_latest_versions",
        lambda: {"policyengine_us": "2.9.0"},
    )

    assert check_updates.main() == 0
    assert weekly_project.read_text() == original
    mock_pypi.assert_not_called()


def test_metadata_failure_does_not_write_partial_update(
    check_updates, weekly_project, mock_pypi, monkeypatch, tmp_path
):
    original = weekly_project.read_text()
    monkeypatch.setattr(
        check_updates,
        "get_latest_versions",
        lambda: {"policyengine_us": "2.17.2"},
    )
    mock_pypi.side_effect = requests.HTTPError("PyPI unavailable")

    with pytest.raises(requests.HTTPError, match="PyPI unavailable"):
        check_updates.main()

    assert weekly_project.read_text() == original
    assert not (tmp_path / "pr_summary.md").exists()
