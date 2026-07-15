import pytest

from tests.fixtures.country import (
    valid_household_requesting_ctc_calculation,
    country_package_name_us,
    country_id_us,
)
from tests.data.uk_households import (
    uk_household_requesting_universal_credit,
    uk_household_requesting_enum_outputs,
    uk_household_requesting_income_tax,
    uk_household_with_axes,
    uk_personal_allowance_reform,
)
from importlib.metadata import PackageNotFoundError
from policyengine_household_api.country import (
    COUNTRIES,
    PolicyEngineCountry,
)
from policyengine_household_api.constants import COUNTRY_PACKAGE_VERSIONS


class TestCalculateReturnValue:
    def test_calculate_returns_household_result(self):
        # Given a valid country calculation under current law
        country = PolicyEngineCountry(country_package_name_us, country_id_us)

        # When the calculate method is called
        result = country.calculate(
            household=valid_household_requesting_ctc_calculation,
            reform=None,
        )

        assert isinstance(result, dict)
        assert "people" in result


@pytest.fixture(scope="module")
def uk_country():
    # Reuse the instance the endpoints serve instead of building a second
    # UK tax-benefit system; these tests exercise the same object.
    return COUNTRIES["uk"]


class TestCalculateUK:
    """policyengine-uk >= 2.43 exposes a wrapper Simulation that no longer
    accepts a tax_benefit_system argument; these tests pin the alternate
    construction path in PolicyEngineCountry.calculate.
    """

    def test_calculate_returns_universal_credit(self, uk_country):
        # Given a single parent with one child renting in London
        result = uk_country.calculate(
            household=uk_household_requesting_universal_credit,
            reform=None,
        )

        universal_credit = result["benunits"]["benunit"]["universal_credit"][
            "2026"
        ]
        assert isinstance(universal_credit, float)
        assert universal_credit > 0

    def test_calculate_decodes_enum_outputs(self, uk_country):
        # Wrapper-style Simulations return enum results as plain string
        # arrays rather than EnumArray; the response loop must serialize
        # them to the enum's name either way.
        result = uk_country.calculate(
            household=uk_household_requesting_enum_outputs,
            reform=None,
        )

        country = result["households"]["household"]["country"]["2026"]
        assert country == "ENGLAND"

    def test_calculate_applies_parametric_reform(self, uk_country):
        baseline = uk_country.calculate(
            household=uk_household_requesting_income_tax,
            reform=None,
        )
        reformed = uk_country.calculate(
            household=uk_household_requesting_income_tax,
            reform=uk_personal_allowance_reform,
        )

        baseline_tax = baseline["people"]["parent"]["income_tax"]["2026"]
        reformed_tax = reformed["people"]["parent"]["income_tax"]["2026"]
        # Raising the personal allowance above this person's employment
        # income must reduce their income tax to zero.
        assert baseline_tax > 0
        assert reformed_tax == 0

    def test_calculate_supports_axes(self, uk_country):
        result = uk_country.calculate(
            household=uk_household_with_axes,
            reform=None,
        )

        universal_credit = result["benunits"]["benunit"]["universal_credit"][
            "2026"
        ]
        assert isinstance(universal_credit, list)
        assert len(universal_credit) == 3
        # Universal Credit tapers away as swept employment income rises.
        assert universal_credit[0] > universal_credit[-1]


class TestPolicyEngineBundle:
    def test_country_exposes_policyengine_bundle(self):
        country = PolicyEngineCountry(country_package_name_us, country_id_us)

        assert country.policyengine_bundle == {
            "model_version": COUNTRY_PACKAGE_VERSIONS[country_id_us],
            "data_version": None,
            "dataset": None,
        }
        assert (
            country.metadata["result"]["version"]
            == COUNTRY_PACKAGE_VERSIONS[country_id_us]
        )


def test_country_package_versions_falls_back_per_package(monkeypatch):
    from policyengine_household_api import constants

    def _fake_version(package_name: str) -> str:
        if package_name == "policyengine_us":
            return "1.602.0"
        raise PackageNotFoundError(package_name)

    monkeypatch.setattr(constants, "version", _fake_version)

    versions = {}
    for country, package_name in zip(
        constants.COUNTRIES, constants.COUNTRY_PACKAGE_NAMES
    ):
        try:
            versions[country] = constants.version(package_name)
        except Exception:
            versions[country] = "0.0.0"

    assert versions["us"] == "1.602.0"
    assert versions["uk"] == "0.0.0"
