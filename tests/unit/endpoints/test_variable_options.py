from enum import Enum
from types import SimpleNamespace

import pytest

from policyengine_household_api.country import COUNTRIES


class ProviderChoices(Enum):
    UNSPECIFIED = "Unspecified"
    UTILITY = "Example utility"
    OTHER = "Other provider"


@pytest.fixture
def provider_variables(monkeypatch):
    variables = COUNTRIES["us"].tax_benefit_system.variables
    for variable, states in [
        ("electricity_provider", ["ID", "MT"]),
        ("natural_gas_provider", ["ID", "OR"]),
    ]:
        monkeypatch.setitem(
            variables,
            variable,
            SimpleNamespace(
                possible_values=ProviderChoices,
                metadata={
                    "states_by_value": {
                        "UNSPECIFIED": None,
                        "UTILITY": states,
                        "OTHER": None,
                    }
                },
            ),
        )


@pytest.mark.parametrize(
    "variable, state, named",
    [
        ("electricity_provider", "mt", True),
        ("natural_gas_provider", "MT", False),
        ("electricity_provider", "OR", False),
        ("natural_gas_provider", "OR", True),
        ("natural_gas_provider", "DC", False),
    ],
)
def test_options_filter_by_model_state_and_fuel(
    client, provider_variables, variable, state, named
):
    response = client.get(
        f"/us/variables/{variable}/options", query_string={"state": state}
    )
    assert response.status_code == 200
    options = [{"value": "UNSPECIFIED", "label": "Unspecified"}]
    if named:
        options.append({"value": "UTILITY", "label": "Example utility"})
    options.append({"value": "OTHER", "label": "Other provider"})
    assert response.json == {"status": "ok", "result": options}


@pytest.mark.parametrize("query", [{}, {"state": "ZZ"}])
def test_options_require_valid_state(client, provider_variables, query):
    response = client.get(
        "/us/variables/electricity_provider/options", query_string=query
    )
    assert response.status_code == 400
    assert response.json["status"] == "error"


@pytest.mark.parametrize("variable", ["unknown_variable", "state_code"])
def test_model_without_state_mapping_returns_404(client, variable):
    response = client.get(f"/us/variables/{variable}/options?state=IL")
    assert response.status_code == 404
    assert response.json["status"] == "error"
