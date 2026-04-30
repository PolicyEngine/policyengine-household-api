import importlib
import logging
from flask import Response
import json
from policyengine_core.taxbenefitsystems import TaxBenefitSystem
from policyengine_household_api.constants import COUNTRY_PACKAGE_VERSIONS
from typing import Union
from policyengine_household_api.utils import (
    get_safe_json,
    generate_computation_tree,
)
from policyengine_household_api.models.computation_tree import (
    ComputationTree,
    EntityDescription,
)
from policyengine_household_api.utils.google_cloud import (
    GoogleCloudStorageManager,
)
from policyengine_core.parameters import (
    ParameterNode,
    Parameter,
    ParameterScale,
    ParameterScaleBracket,
)
from policyengine_core.parameters import get_parameter
from policyengine_core.model_api import Reform, Enum
from policyengine_core.periods import instant, period as parse_period
import copy
import dpath
import math
from dataclasses import dataclass
from uuid import UUID, uuid4


# ---------------------------------------------------------------------------
# Period key parsing
# ---------------------------------------------------------------------------
#
# policyengine-core's `period(value)` is the canonical parser for situation
# period keys. It returns a Period whose `unit` is one of "year" / "month" /
# "day", and raises ValueError on garbage input. The household API only
# distinguishes year vs. month, so we wrap that parser here.


def _parsed_period(period_key: str):
    """Return a Period for a string key, or None if it doesn't parse.

    Wrapping policyengine-core's parser keeps the rest of this module free
    of regex and gives one place to handle malformed keys (e.g. ``"2026-15"``).
    """
    try:
        return parse_period(period_key)
    except (TypeError, ValueError):
        return None


def _is_year_key(period_key: str) -> bool:
    parsed = _parsed_period(period_key)
    return parsed is not None and parsed.unit == "year"


def _month_key_year(period_key: str) -> str | None:
    """Return the four-digit year if ``period_key`` parses as a month, else None."""
    parsed = _parsed_period(period_key)
    if parsed is None or parsed.unit != "month":
        return None
    return f"{parsed.start.year:04d}"


def _is_numeric(value) -> bool:
    """True for int/float numerics; rejects bool because ``bool`` ⊂ ``int`` in Python."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


# ---------------------------------------------------------------------------
# Household walk
# ---------------------------------------------------------------------------
#
# Validation, warning detection, and YEAR-key expansion all need the same
# household traversal: skip the top-level ``axes`` list, descend into each
# entity instance, and yield each ``(variable, period_map)`` pair. A single
# slot walker lets each pass focus on its rule instead of repeating the
# nested-loop boilerplate.


@dataclass(frozen=True)
class _VariableSlot:
    """A located period-map for one variable on one entity instance.

    ``period_map`` is the live dict, so callers that want to mutate it
    (the normalizer) and callers that only read (the validators and the
    warning detector) can share the same iterator.
    """

    entity_plural: str
    entity_id: str
    variable_name: str
    variable: object
    period_map: dict


def _walk_variable_slots(household: dict, system):
    """Yield a ``_VariableSlot`` for every (entity, variable) period map.

    Skips the top-level ``axes`` list, any non-dict value, and any
    variable name the system doesn't recognize (Pydantic rejects unknown
    names upstream; this is defense-in-depth so a stray key can't crash
    the walk).
    """
    for entity_plural, entities in (household or {}).items():
        if entity_plural == "axes" or not isinstance(entities, dict):
            continue
        for entity_id, entity_data in entities.items():
            if not isinstance(entity_data, dict):
                continue
            for variable_name, period_map in entity_data.items():
                if not isinstance(period_map, dict):
                    continue
                variable = system.variables.get(variable_name)
                if variable is None:
                    continue
                yield _VariableSlot(
                    entity_plural=entity_plural,
                    entity_id=entity_id,
                    variable_name=variable_name,
                    variable=variable,
                    period_map=period_map,
                )


# ---------------------------------------------------------------------------
# Period-key validation
# ---------------------------------------------------------------------------


def validate_period_keys(household: dict, system) -> None:
    """Reject any period key that doesn't parse as a year or month.

    policyengine-core's ``period()`` raises on malformed strings; without
    this check the engine would silently ignore the slot and the partner
    would see a confusing zero. Surfacing it as a 400 with the offending
    key gives them an explicit signal. Pydantic doesn't validate
    period-key strings today, so this is the single defensive checkpoint.
    """
    for slot in _walk_variable_slots(household, system):
        for period_key in slot.period_map:
            if _parsed_period(period_key) is None:
                raise ValueError(
                    f"Invalid period key `{period_key}` for "
                    f"`{slot.variable_name}` on "
                    f"`{slot.entity_plural}/{slot.entity_id}`. "
                    f'Expected a year (e.g. "2026") or a month '
                    f'(e.g. "2026-01").'
                )


# ---------------------------------------------------------------------------
# Period-shape warnings
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PartialMonthlyInputWarning:
    """Partial-month input on a MONTH-defined variable, paired with an
    annual output request on another MONTH-defined variable for the same
    year. The unset months read the engine's fallback (often 0, sometimes
    a formula-derived value) and silently inflate the annual sum.
    """

    variable: str
    entity_plural: str
    entity_id: str
    year: str
    months_set: tuple[int, ...]

    @property
    def message(self) -> str:
        sample = ", ".join(f"{self.year}-{m:02d}" for m in self.months_set[:3])
        if len(self.months_set) > 3:
            sample += ", ..."
        missing = 12 - len(self.months_set)
        return (
            f"`{self.variable}` on `{self.entity_plural}/{self.entity_id}` was keyed "
            f"for {len(self.months_set)} of 12 months in {self.year} ({sample}); "
            f"the remaining {missing} months will read the engine's "
            f"fallback value (often 0, sometimes a formula-derived value), "
            f"not the value you set. Because an annual output is requested "
            f"for {self.year}, those fallback values are summed into the annual "
            f"total and may not match what you intended. To get an accurate "
            f'annual figure, either send a yearly key (`{{"{self.year}": V}}`) '
            f"or set all 12 monthly keys."
        )


# Type alias for any warning the detector can emit.
PeriodWarning = PartialMonthlyInputWarning


def detect_period_warnings(household: dict, system) -> list[PeriodWarning]:
    """Return structured warnings for surprising request shapes.

    Currently surfaces one kind of warning:

    - ``PartialMonthlyInputWarning`` — partial monthly input on a
      MONTH-defined variable paired with an annual output request for
      the same year on any MONTH-defined variable. The unset months read
      the engine's fallback (often 0, sometimes a formula-derived value)
      and silently inflate the annual sum.

    The hosted v1 API doesn't emit any warnings; this is purely additive
    partner-facing diagnostic — the numeric output is unchanged.
    """
    warnings: list[PeriodWarning] = []
    annual_month_output_years: set[str] = set()
    monthly_inputs: dict[tuple[str, str, str, str], set[int]] = {}
    # `(variable, entity, year)` tuples whose period map already carries a
    # non-null year-key input. The normalizer fills the unset months from
    # the year-input remainder, so the partial-monthly hazard does not
    # apply — the unset months don't read the engine's fallback.
    years_with_year_input: set[tuple[str, str, str, str]] = set()

    for slot in _walk_variable_slots(household, system):
        is_month_var = slot.variable.definition_period == "month"
        for period_key, value in slot.period_map.items():
            if value is None:
                # Annual nulls on MONTH vars arm the missing-month
                # hazard. YEAR-defined vars don't have months.
                if is_month_var and _is_year_key(period_key):
                    annual_month_output_years.add(period_key)
                continue
            if not is_month_var:
                continue
            if _is_year_key(period_key):
                years_with_year_input.add(
                    (
                        slot.variable_name,
                        slot.entity_plural,
                        slot.entity_id,
                        period_key,
                    )
                )
                continue
            year = _month_key_year(period_key)
            if year is None:
                continue
            parsed = _parsed_period(period_key)
            key = (
                slot.variable_name,
                slot.entity_plural,
                slot.entity_id,
                year,
            )
            monthly_inputs.setdefault(key, set()).add(parsed.start.month)

    for (
        variable_name,
        entity_plural,
        entity_id,
        year,
    ), months in monthly_inputs.items():
        if year not in annual_month_output_years:
            continue
        if len(months) >= 12:
            continue
        # If the same period map also has a non-null year input for this
        # year, the normalizer fills the unset months from the remainder
        # — there's no missing-month hazard to warn about.
        if (
            variable_name,
            entity_plural,
            entity_id,
            year,
        ) in years_with_year_input:
            continue
        warnings.append(
            PartialMonthlyInputWarning(
                variable=variable_name,
                entity_plural=entity_plural,
                entity_id=entity_id,
                year=year,
                months_set=tuple(sorted(months)),
            )
        )
    return warnings


# ---------------------------------------------------------------------------
# Period-key normalization
# ---------------------------------------------------------------------------
#
# When a numeric MONTH-defined variable receives both a year-key and same-
# year monthly-key inputs, the API mirrors the hosted v1 API and OpenFisca's
# ``set_input_divide_by_period``: treat the year value as the annual total,
# subtract any explicit monthly inputs, and split the remainder evenly
# across the unset months (raw float, no rounding). Boolean / string / enum
# year values broadcast to the unset months unchanged. If the explicit
# monthlies sum to more than the annual total, ``validate_period_budgets``
# rejects the request with a 400 (matching the ``ValueError("Inconsistent
# input...")`` that OpenFisca raises in the same situation).


def _is_numeric_value_type(variable) -> bool:
    """True iff the variable's value_type is int or float (excluding bool)."""
    vt = variable.value_type
    return vt in (int, float)


def validate_period_budgets(household: dict, system) -> None:
    """Reject requests where all 12 monthly inputs disagree with the annual.

    For numeric MONTH-defined variables, partners may send both a year key
    (the annual total) and one or more monthly overrides. policyengine-core's
    ``set_input_divide_by_period`` raises ``ValueError("Inconsistent input")``
    in exactly one situation: every month of the year is explicit AND the
    sum of those monthlies doesn't match the annual total. Partial-month
    overrides (any number from 0 to 11 explicit months) are silently
    accepted and the remainder is distributed across the unset months,
    even when the remainder is negative. We mirror that exact rule so
    partner integrations match v1 byte-for-byte.
    """
    for slot in _walk_variable_slots(household, system):
        if slot.variable.definition_period != "month":
            continue
        if not _is_numeric_value_type(slot.variable):
            continue
        _check_year_budget(
            period_map=slot.period_map,
            variable_name=slot.variable_name,
            entity_plural=slot.entity_plural,
            entity_id=slot.entity_id,
        )


def _check_year_budget(
    period_map: dict,
    variable_name: str,
    entity_plural: str,
    entity_id: str,
) -> None:
    for period_key, value in list(period_map.items()):
        if not _is_year_key(period_key):
            continue
        if not _is_numeric(value):
            continue
        year = period_key
        explicit_months: dict[int, float] = {}
        for inner_key, inner_value in period_map.items():
            if _month_key_year(inner_key) != year:
                continue
            if not _is_numeric(inner_value):
                continue
            month = _parsed_period(inner_key).start.month
            explicit_months[month] = float(inner_value)
        # v1 raises only when every month is explicit and the sum
        # disagrees with the annual; partial monthlies are silently
        # distributed (even if the remainder is negative).
        if len(explicit_months) < 12:
            continue
        explicit_sum = sum(explicit_months.values())
        if explicit_sum != float(value):
            raise ValueError(
                f"Inconsistent input: monthly values for `{variable_name}` on "
                f"`{entity_plural}/{entity_id}` in {year} sum to "
                f"{explicit_sum}, which doesn't match the annual total {value}."
            )


def _normalize_period_keys(household: dict, system) -> dict:
    """Return a deep-copied household with YEAR-keyed inputs expanded to months.

    policyengine-core's ``Simulation(situation=...)`` silently drops a year-
    period assignment on a MONTH-defined variable (see issue #1489). The
    hosted v1 API distributes the annual value across the year so partners
    get a sensible answer. To match that behavior, this normalizer walks the
    situation, looks up each variable's ``definition_period``, and rewrites
    YEAR-keyed values for MONTH-defined variables before the engine sees them.

    Behavior per value type:

    - **numeric**: the year value is treated as the annual total. Any
      explicit monthly values for the same year are preserved (they
      override that month) and the remainder ``V − sum(explicit)`` is
      split evenly across the unset months as a raw float — matches
      v1's ``163.63637``-style emission. Rounding here would introduce
      drift the engine sums back differently.
    - **boolean / string / enum**: the year value is broadcast unchanged
      to the unset months. Explicit monthly values still override.
    - **null (output request)**: the YEAR key is left alone so the engine
      returns the annual sum across the 12 monthly values.

    The original household is never mutated, so the response can echo the
    partner's keys verbatim.
    """
    normalized = copy.deepcopy(household)
    for slot in _walk_variable_slots(normalized, system):
        if slot.variable.definition_period != "month":
            continue
        _expand_year_keys_in_place(slot.period_map, slot.variable)
    return normalized


def _expand_year_keys_in_place(period_map: dict, variable) -> None:
    is_numeric = _is_numeric_value_type(variable)
    for period_key in list(period_map.keys()):
        if not _is_year_key(period_key):
            continue
        value = period_map[period_key]
        if value is None:
            # Output request — keep the YEAR key so the engine sums the months.
            continue
        year = period_key
        if is_numeric and _is_numeric(value):
            _distribute_numeric_year_value(period_map, year, float(value))
        else:
            _broadcast_year_value(period_map, year, value)


def _distribute_numeric_year_value(
    period_map: dict, year: str, annual_value: float
) -> None:
    """Distribute an annual numeric V across the 12 months of ``year``.

    Explicit monthly values for the same year are preserved (the partner
    is overriding that month). The remainder ``V − sum(explicit)`` is
    split evenly across the unset months as a raw float, matching the
    hosted v1 API and OpenFisca's ``set_input_divide_by_period`` —
    including the case where the remainder is negative (sum of explicit
    months > annual). ``validate_period_budgets`` only rejects the
    fully-explicit-12-months case where sum != annual; partial monthlies
    are silently distributed even if that pushes the unset months
    negative, exactly like v1.
    """
    explicit_months: dict[int, float] = {}
    for inner_key, inner_value in period_map.items():
        if _month_key_year(inner_key) != year:
            continue
        if not _is_numeric(inner_value):
            continue
        month = _parsed_period(inner_key).start.month
        explicit_months[month] = float(inner_value)

    unset_count = 12 - len(explicit_months)
    if unset_count <= 0:
        # All 12 months are explicit. validate_period_budgets has already
        # confirmed they sum to == annual_value, so just remove the YEAR key.
        del period_map[year]
        return

    remainder = annual_value - sum(explicit_months.values())
    per_unset = remainder / unset_count
    del period_map[year]
    for month in range(1, 13):
        month_key = f"{year}-{month:02d}"
        if month in explicit_months:
            continue
        # Overwrite missing slots and None (output-request) slots; explicit
        # non-null monthly inputs are already in `explicit_months` so this
        # branch only fires for unset / null slots.
        if period_map.get(month_key) is None:
            period_map[month_key] = per_unset


def _broadcast_year_value(period_map: dict, year: str, value) -> None:
    """Broadcast a non-numeric annual value (bool/str/enum) to every month.

    Explicit monthly values already in the period map win — partners can
    set a year-wide value and override one month explicitly.
    """
    del period_map[year]
    for month in range(1, 13):
        month_key = f"{year}-{month:02d}"
        if period_map.get(month_key) is None:
            period_map[month_key] = value


class PolicyEngineCountry:
    def __init__(self, country_package_name: str, country_id: str):
        self.country_package_name = country_package_name
        self.country_id = country_id
        self.country_package = importlib.import_module(country_package_name)
        self.tax_benefit_system: TaxBenefitSystem = (
            self.country_package.CountryTaxBenefitSystem()
        )
        self.policyengine_bundle = self.build_policyengine_bundle()
        self.build_metadata()

    def build_policyengine_bundle(self) -> dict:
        return {
            "model_version": COUNTRY_PACKAGE_VERSIONS[self.country_id],
            "data_version": None,
            "dataset": None,
        }

    def build_metadata(self):
        self.metadata = dict(
            status="ok",
            message=None,
            result=dict(
                variables=self.build_variables(),
                parameters=self.build_parameters(),
                entities=self.build_entities(),
                variableModules=self.tax_benefit_system.variable_module_metadata,
                economy_options=self.build_microsimulation_options(),
                current_law_id={
                    "uk": 1,
                    "us": 2,
                    "ca": 3,
                    "ng": 4,
                    "il": 5,
                }[self.country_id],
                basicInputs=self.tax_benefit_system.basic_inputs,
                modelled_policies=self.tax_benefit_system.modelled_policies,
                version=self.policyengine_bundle["model_version"],
            ),
        )

    def build_microsimulation_options(self) -> dict:
        # { region: [{ name: "uk", label: "the UK" }], time_period: [{ name: 2022, label: "2022", ... }] }
        options = dict()
        if self.country_id == "uk":
            region = [
                dict(name="uk", label="the UK"),
                dict(name="eng", label="England"),
                dict(name="scot", label="Scotland"),
                dict(name="wales", label="Wales"),
                dict(name="ni", label="Northern Ireland"),
            ]
            time_period = [
                dict(name=2023, label="2023"),
                dict(name=2024, label="2024"),
                dict(name=2022, label="2022"),
            ]
            options["region"] = region
            options["time_period"] = time_period
        elif self.country_id == "us":
            region = [
                dict(name="us", label="the US"),
                dict(name="enhanced_us", label="the US (enhanced CPS)"),
                dict(name="al", label="Alabama"),
                dict(name="ak", label="Alaska"),
                dict(name="az", label="Arizona"),
                dict(name="ar", label="Arkansas"),
                dict(name="ca", label="California"),
                dict(name="co", label="Colorado"),
                dict(name="ct", label="Connecticut"),
                dict(name="de", label="Delaware"),
                dict(name="dc", label="District of Columbia"),
                dict(name="fl", label="Florida"),
                dict(name="ga", label="Georgia"),
                dict(name="hi", label="Hawaii"),
                dict(name="id", label="Idaho"),
                dict(name="il", label="Illinois"),
                dict(name="in", label="Indiana"),
                dict(name="ia", label="Iowa"),
                dict(name="ks", label="Kansas"),
                dict(name="ky", label="Kentucky"),
                dict(name="la", label="Louisiana"),
                dict(name="me", label="Maine"),
                dict(name="md", label="Maryland"),
                dict(name="ma", label="Massachusetts"),
                dict(name="mi", label="Michigan"),
                dict(name="mn", label="Minnesota"),
                dict(name="ms", label="Mississippi"),
                dict(name="mo", label="Missouri"),
                dict(name="mt", label="Montana"),
                dict(name="ne", label="Nebraska"),
                dict(name="nv", label="Nevada"),
                dict(name="nh", label="New Hampshire"),
                dict(name="nj", label="New Jersey"),
                dict(name="nm", label="New Mexico"),
                dict(name="ny", label="New York"),
                dict(name="nyc", label="New York City"),  # Region, not State
                dict(name="nc", label="North Carolina"),
                dict(name="nd", label="North Dakota"),
                dict(name="oh", label="Ohio"),
                dict(name="ok", label="Oklahoma"),
                dict(name="or", label="Oregon"),
                dict(name="pa", label="Pennsylvania"),
                dict(name="ri", label="Rhode Island"),
                dict(name="sc", label="South Carolina"),
                dict(name="sd", label="South Dakota"),
                dict(name="tn", label="Tennessee"),
                dict(name="tx", label="Texas"),
                dict(name="ut", label="Utah"),
                dict(name="vt", label="Vermont"),
                dict(name="va", label="Virginia"),
                dict(name="wa", label="Washington"),
                dict(name="wv", label="West Virginia"),
                dict(name="wi", label="Wisconsin"),
                dict(name="wy", label="Wyoming"),
            ]
            time_period = [
                dict(name=2023, label="2023"),
                dict(name=2022, label="2022"),
                dict(name=2021, label="2021"),
            ]
            options["region"] = region
            options["time_period"] = time_period
        elif self.country_id == "ca":
            region = [
                dict(name="ca", label="Canada"),
            ]
            time_period = [
                dict(name=2023, label="2023"),
            ]
            options["region"] = region
            options["time_period"] = time_period
        elif self.country_id == "ng":
            region = [
                dict(name="ng", label="Nigeria"),
            ]
            time_period = [
                dict(name=2023, label="2023"),
            ]
            options["region"] = region
            options["time_period"] = time_period
        elif self.country_id == "il":
            region = [
                dict(name="il", label="Israel"),
            ]
            time_period = [
                dict(name=2023, label="2023"),
            ]
            options["region"] = region
            options["time_period"] = time_period
        return options

    def build_variables(self) -> dict:
        variables = self.tax_benefit_system.variables
        variable_data = {}
        for variable_name, variable in variables.items():
            variable_data[variable_name] = {
                "documentation": variable.documentation,
                "entity": variable.entity.key,
                "valueType": variable.value_type.__name__,
                "definitionPeriod": variable.definition_period,
                "name": variable_name,
                "label": variable.label,
                "category": variable.category,
                "unit": variable.unit,
                "moduleName": variable.module_name,
                "indexInModule": variable.index_in_module,
                "isInputVariable": variable.is_input_variable(),
                "defaultValue": (
                    variable.default_value
                    if isinstance(variable.default_value, (int, float, bool))
                    else None
                ),
                "adds": variable.adds,
                "subtracts": variable.subtracts,
                "hidden_input": variable.hidden_input,
            }
            if variable.value_type.__name__ == "Enum":
                variable_data[variable_name]["possibleValues"] = [
                    dict(value=value.name, label=value.value)
                    for value in variable.possible_values
                ]
                variable_data[variable_name]["defaultValue"] = (
                    variable.default_value.name
                )
        return variable_data

    def build_parameters(self) -> dict:
        parameters = self.tax_benefit_system.parameters
        parameter_data = {}
        for parameter in parameters.get_descendants():
            if "gov" != parameter.name[:3]:
                continue
            end_name = parameter.name.split(".")[-1]
            if isinstance(parameter, ParameterScale):
                parameter_data[parameter.name] = {
                    "type": "parameterNode",
                    "parameter": parameter.name,
                    "description": parameter.description,
                    "label": parameter.metadata.get(
                        "label", end_name.replace("_", " ")
                    ),
                }
            elif isinstance(parameter, ParameterScaleBracket):
                bracket_index = int(
                    parameter.name[parameter.name.index("[") + 1 : -1]
                )
                # Set the label to 'first bracket' for the first bracket, 'second bracket' for the second, etc.
                bracket_label = f"bracket {bracket_index + 1}"
                parameter_data[parameter.name] = {
                    "type": "parameterNode",
                    "parameter": parameter.name,
                    "description": parameter.description,
                    "label": parameter.metadata.get("label", bracket_label),
                }
            elif isinstance(parameter, Parameter):
                parameter_data[parameter.name] = {
                    "type": "parameter",
                    "parameter": parameter.name,
                    "description": parameter.description,
                    "label": parameter.metadata.get(
                        "label", end_name.replace("_", " ")
                    ),
                    "unit": parameter.metadata.get("unit"),
                    "period": parameter.metadata.get("period"),
                    "values": {
                        value_at_instant.instant_str: get_safe_json(
                            value_at_instant.value
                        )
                        for value_at_instant in parameter.values_list
                    },
                    "economy": parameter.metadata.get("economy", True),
                    "household": parameter.metadata.get("household", True),
                }
            elif isinstance(parameters, ParameterNode):
                parameter_data[parameter.name] = {
                    "type": "parameterNode",
                    "parameter": parameter.name,
                    "description": parameter.description,
                    "label": parameter.metadata.get(
                        "label", end_name.replace("_", " ")
                    ),
                    "economy": parameter.metadata.get("economy", True),
                    "household": parameter.metadata.get("household", True),
                }
        return parameter_data

    def build_entities(self) -> dict:
        data = {}
        for entity in self.tax_benefit_system.entities:
            entity_data = {
                "plural": entity.plural,
                "label": entity.label,
                "doc": entity.doc,
                "is_person": entity.is_person,
                "key": entity.key,
            }
            if hasattr(entity, "roles"):
                entity_data["roles"] = {
                    role.key: {
                        "plural": role.plural,
                        "label": role.label,
                        "doc": role.doc,
                    }
                    for role in entity.roles
                }
            else:
                entity_data["roles"] = {}
            data[entity.key] = entity_data
        return data

    def calculate(
        self,
        household: dict,
        reform: Union[dict, None] = None,
        enable_ai_explainer: bool = False,
    ):
        if reform is not None and len(reform.keys()) > 0:
            system = self.tax_benefit_system.clone()
            for parameter_name in reform:
                for time_period, value in reform[parameter_name].items():
                    start_instant, end_instant = time_period.split(".")
                    parameter = get_parameter(
                        system.parameters, parameter_name
                    )
                    node_type = type(parameter.values_list[-1].value)
                    if node_type is int:
                        node_type = float
                    try:
                        value = float(value)
                    except (TypeError, ValueError):
                        pass
                    parameter.update(
                        start=instant(start_instant),
                        stop=instant(end_instant),
                        value=node_type(value),
                    )
        else:
            system = self.tax_benefit_system

        # Hand a normalized copy to the engine so YEAR-keyed inputs on
        # MONTH-defined variables behave like the hosted v1 API instead of
        # being silently dropped (issue #1489). The normalizer deep-copies
        # internally so the original `household` is intact and the response
        # can echo back the partner's keys.
        normalized_household = _normalize_period_keys(household, system)

        simulation = self.country_package.Simulation(
            tax_benefit_system=system,
            situation=normalized_household,
        )

        # Independent clone for the response-building loop below, which
        # mutates `household` to fill in computed values. Not related to
        # the normalizer above — that one's already a separate copy.
        household = json.loads(json.dumps(household))

        # Run tracer on household
        simulation.trace = True
        requested_computations = get_requested_computations(household)

        for (
            entity_plural,
            entity_id,
            variable_name,
            period,
        ) in requested_computations:
            try:
                variable = system.get_variable(variable_name)
                result = simulation.calculate(variable_name, period)
                population = simulation.get_population(entity_plural)
                if "axes" in household:
                    count_entities = len(household[entity_plural])
                    entity_index = 0
                    for _entity_id in household[entity_plural].keys():
                        if _entity_id == entity_id:
                            break
                        entity_index += 1
                    result = (
                        result.astype(float)
                        .reshape((-1, count_entities))
                        .T[entity_index]
                        .tolist()
                    )
                    # If the result contains infinities, throw an error
                    if any([math.isinf(value) for value in result]):
                        raise ValueError("Infinite value")
                    else:
                        household[entity_plural][entity_id][variable_name][
                            period
                        ] = result
                else:
                    entity_index = population.get_index(entity_id)
                    if variable.value_type == Enum:
                        entity_result = result.decode()[entity_index].name
                    elif variable.value_type is float:
                        entity_result = float(str(result[entity_index]))
                        # Convert infinities to JSON infinities
                        if entity_result == float("inf"):
                            entity_result = "Infinity"
                        elif entity_result == float("-inf"):
                            entity_result = "-Infinity"
                    elif variable.value_type is str:
                        entity_result = str(result[entity_index])
                    else:
                        entity_result = result.tolist()[entity_index]

                    household[entity_plural][entity_id][variable_name][
                        period
                    ] = entity_result
            except Exception as e:
                if "axes" in household:
                    pass
                else:
                    household[entity_plural][entity_id][variable_name][
                        period
                    ] = None
                    print(
                        f"Error computing {variable_name} for {entity_id}: {e}"
                    )

        # Execute all household tracer operations
        try:
            if enable_ai_explainer:
                entity_description = EntityDescription.model_validate(
                    simulation.describe_entities()
                )

                # Generate tracer output
                log_lines: list = generate_computation_tree(simulation)

                # Take the tracer output and create a new tracer object,
                # storing in Google Cloud bucket
                computation_tree_uuid: UUID = uuid4()
                computation_tree_record: ComputationTree = ComputationTree(
                    uuid=computation_tree_uuid,
                    country_id=self.country_id,
                    tree=log_lines,
                    entity_description=entity_description,
                )

                storage_manager = GoogleCloudStorageManager()
                storage_manager.store(
                    uuid=computation_tree_uuid,
                    data=computation_tree_record,
                )

                # Return the household and the tracer's UUID
                return household, str(computation_tree_uuid)

            return household, None

        except Exception:
            # Re-raise so endpoints/household.py (which unpacks
            # ``(result, computation_tree_uuid)``) can surface a real
            # 500 instead of a TypeError on ``None`` unpacking.
            logging.exception("Tracer failed while computing household")
            raise


def create_policy_reform(policy_data: dict) -> dict:
    """
    Create a policy reform.

    Args:
        policy_data (dict): The policy data.

    Returns:
        dict: The reform.
    """

    def modify_parameters(parameters: ParameterNode) -> ParameterNode:
        for path, values in policy_data.items():
            node = parameters
            for step in path.split("."):
                if "[" in step:
                    step, index = step.split("[")
                    index = int(index[:-1])
                    node = node.children[step].brackets[index]
                else:
                    node = node.children[step]
            for period, value in values.items():
                start, end = period.split(".")
                node_type = type(node.values_list[-1].value)
                if node_type is int:
                    node_type = float  # '0' is of type int by default, but usually we want to cast to float.
                node.update(
                    start=instant(start),
                    stop=instant(end),
                    value=node_type(value),
                )

        return parameters

    class reform(Reform):
        def apply(self):
            self.modify_parameters(modify_parameters)

    return reform


def get_requested_computations(household: dict):
    requested_computations = dpath.search(
        household,
        "*/*/*/*",
        afilter=lambda t: t is None,
        yielded=True,
    )
    requested_computation_data = []

    for computation in requested_computations:
        path = computation[0]
        entity_plural, entity_id, variable_name, period = path.split("/")
        requested_computation_data.append(
            (entity_plural, entity_id, variable_name, period)
        )

    return requested_computation_data


COUNTRIES = {
    "uk": PolicyEngineCountry("policyengine_uk", "uk"),
    "us": PolicyEngineCountry("policyengine_us", "us"),
    "ca": PolicyEngineCountry("policyengine_canada", "ca"),
    "ng": PolicyEngineCountry("policyengine_ng", "ng"),
    "il": PolicyEngineCountry("policyengine_il", "il"),
}


def validate_country(country_id: str) -> Union[None, Response]:
    """Validate that a country ID is valid. If not, return a 404 response.

    Args:
        country_id (str): The country ID to validate.

    Returns:

    """
    if country_id not in COUNTRIES:
        body = dict(
            status="error",
            message=f"Country {country_id} not found. Available countries are: {', '.join(COUNTRIES.keys())}",
        )
        return Response(json.dumps(body), status=404)
    return None
