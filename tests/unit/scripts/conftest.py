import importlib.util
from pathlib import Path
from unittest.mock import Mock

import pytest


@pytest.fixture
def check_updates():
    path = (
        Path(__file__).resolve().parents[3]
        / ".github/scripts/check_updates.py"
    )
    spec = importlib.util.spec_from_file_location("weekly_check_updates", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def weekly_project(tmp_path, monkeypatch):
    pyproject = tmp_path / "libs/household-api/pyproject.toml"
    pyproject.parent.mkdir(parents=True)
    pyproject.write_text(
        "[project]\ndependencies = [\n"
        '    "policyengine_us==2.9.0",\n'
        '    "policyengine-core==3.30.3",\n'
        '    "policyengine_uk==2.88.18",\n'
        '    "flask>=3.1.3",\n'
        "]\n"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "github-output"))
    return pyproject


@pytest.fixture
def pypi_metadata():
    return {
        "https://pypi.org/pypi/policyengine-us/2.17.2/json": {
            "info": {"requires_dist": ["policyengine-core>=3.32.8"]}
        },
        "https://pypi.org/pypi/policyengine-core/json": {
            "releases": {
                "3.32.10": [{"yanked": False}],
                "3.32.8": [{"yanked": False}],
                "3.30.3": [{"yanked": False}],
            }
        },
    }


@pytest.fixture
def mock_pypi(check_updates, pypi_metadata, monkeypatch):
    def get_response(url, **kwargs):
        response = Mock()
        response.json.return_value = pypi_metadata[url]
        return response

    mock = Mock(side_effect=get_response)
    monkeypatch.setattr(check_updates.requests, "get", mock)
    return mock
