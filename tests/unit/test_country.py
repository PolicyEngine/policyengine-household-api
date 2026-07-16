import pytest

from policyengine_core.parameters import Parameter

from tests.fixtures.country import (
    valid_household_requesting_ctc_calculation,
    country_package_name_us,
    country_id_us,
    us_household_requesting_income_tax,
    us_household_with_axes,
    us_standard_deduction_reform,
)
from tests.data.uk_households import (
    uk_household_requesting_universal_credit,
    uk_household_requesting_enum_outputs,
    uk_household_requesting_income_tax,
    uk_household_married_requesting_marriage_allowance,
    uk_household_with_axes,
    uk_marriage_allowance_structural_reform,
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

    def test_calculate_applies_parametric_reform(self):
        # Pins the standard (core-style) builder's reform path: a routing
        # mistake that sends the policy dict to the Simulation constructor
        # (which expects a Reform class there) breaks every US reform
        # request. The value is a string on purpose: the API casts reform
        # values to the parameter's node type.
        country = COUNTRIES["us"]

        baseline = country.calculate(
            household=us_household_requesting_income_tax,
            reform=None,
        )
        reformed = country.calculate(
            household=us_household_requesting_income_tax,
            reform=us_standard_deduction_reform,
        )

        baseline_tax = baseline["tax_units"]["tax_unit"]["income_tax"]["2024"]
        reformed_tax = reformed["tax_units"]["tax_unit"]["income_tax"]["2024"]
        # Raising the standard deduction must reduce income tax.
        assert reformed_tax < baseline_tax

    def test_calculate_supports_axes(self):
        # Pins the standard axes reshaping path shared by US/CA/NG/IL.
        country = COUNTRIES["us"]

        result = country.calculate(
            household=us_household_with_axes,
            reform=None,
        )

        income_tax = result["tax_units"]["tax_unit"]["income_tax"]["2024"]
        assert isinstance(income_tax, list)
        assert len(income_tax) == 3
        # Income tax rises with swept employment income.
        assert income_tax[-1] > income_tax[0]


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

    def test_calculate_applies_structural_trigger_reform(self, uk_country):
        # The wrapper creates structural reforms from parameter values
        # during construction, so the reform must be applied before that
        # point (Scenario with applied_before_data_load=True). If it is
        # applied late — the wrapper's default for `reform=` — the
        # parameter changes but the structural reform never activates and
        # this household gets baseline (zero) marriage allowance.
        baseline = uk_country.calculate(
            household=uk_household_married_requesting_marriage_allowance,
            reform=None,
        )
        reformed = uk_country.calculate(
            household=uk_household_married_requesting_marriage_allowance,
            reform=uk_marriage_allowance_structural_reform,
        )

        baseline_ma = baseline["people"]["earner"]["marriage_allowance"][
            "2026"
        ]
        reformed_ma = reformed["people"]["earner"]["marriage_allowance"][
            "2026"
        ]
        assert baseline_ma == 0
        assert reformed_ma > 0

    def test_uk_package_exposes_scenario_interface(self, uk_country):
        # _build_simulation_uk resolves Scenario per request; if a future
        # policyengine-uk moves or renames it (or drops from_reform /
        # applied_before_data_load), UK reform requests would 500 at
        # runtime with a raw AttributeError — and the deployed smoke
        # tests send no policy, so deploy gates wouldn't notice. Pin the
        # interface here so a version bump fails in CI instead.
        scenario_cls = uk_country.country_package.Scenario
        scenario = scenario_cls.from_reform(
            {
                "gov.hmrc.income_tax.allowances.personal_allowance.amount": {
                    "2026-01-01.2026-12-31": 15_000.0,
                }
            }
        )
        scenario.applied_before_data_load = True
        assert scenario.applied_before_data_load is True

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

        # Enum outputs under axes come back as decoded names on the UK
        # path (the standard path returns numeric enum indices).
        country = result["households"]["household"]["country"]["2026"]
        assert country == ["ENGLAND", "ENGLAND", "ENGLAND"]


class TestCastReformValue:
    @staticmethod
    def _parameter(values: dict) -> Parameter:
        return Parameter("test.parameter", data={"values": values})

    def test_numeric_strings_cast_to_float(self):
        parameter = self._parameter({"2020-01-01": 100})

        cast = PolicyEngineCountry._cast_reform_value(parameter, "30000")

        assert cast == 30_000.0
        assert isinstance(cast, float)

    @pytest.mark.parametrize(
        "value,expected",
        [
            (True, True),
            (False, False),
            ("true", True),
            ("false", False),
            ("1", True),
            ("0", False),
            (1, True),
            (0, False),
            (1.0, True),
            (0.0, False),
        ],
    )
    def test_boolean_values_cast_explicitly(self, value, expected):
        parameter = self._parameter({"2020-01-01": False})

        assert (
            PolicyEngineCountry._cast_reform_value(parameter, value)
            is expected
        )

    @pytest.mark.parametrize(
        "value",
        [
            "garbage",
            # Deliberately rejected: the pre-rewrite casting accepted
            # these by accident (strings via float-then-bool, None
            # coercing to False, any nonzero number via bool()); they
            # are ambiguous as booleans and now raise instead of
            # silently coercing. Only 0 and 1 are accepted as numbers.
            "2",
            "1.0",
            None,
            2,
            -3,
            2.5,
        ],
    )
    def test_unrecognized_boolean_values_raise(self, value):
        parameter = self._parameter({"2020-01-01": False})

        with pytest.raises(ValueError, match="as a boolean"):
            PolicyEngineCountry._cast_reform_value(parameter, value)

    def test_type_comes_from_most_recent_non_null_value(self):
        # values_list is ordered newest-first; a null placeholder at
        # either end carries no type information and must be skipped.
        parameter = self._parameter({"2015-01-01": None, "2020-01-01": 0.25})

        assert PolicyEngineCountry._cast_reform_value(parameter, "0.3") == 0.3


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
