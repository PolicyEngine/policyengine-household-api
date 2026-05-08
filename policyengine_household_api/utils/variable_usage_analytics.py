"""Privacy-safe variable usage extraction for calculate analytics."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Literal

from policyengine_household_api.utils.deprecated_inputs import (
    DEPRECATED_VARIABLES,
)
from policyengine_household_api.utils.household import VARIABLE_BLACKLIST


VariableSource = Literal[
    "household_input", "requested_output", "mixed", "axis"
]
AvailabilityStatus = Literal[
    "supported", "deprecated_allowlisted", "unsupported"
]
PeriodGranularity = Literal["year", "month", "day", "mixed", "none", "unknown"]


YEAR_RE = re.compile(r"^\d{4}$")
MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class VariableUsageSummary:
    """A grouped, value-free variable usage record for one request."""

    variable_name: str
    request_entity_group: str
    source: VariableSource
    period_granularity: PeriodGranularity
    entity_count: int
    period_count: int
    occurrence_count: int
    availability_status: AvailabilityStatus
    model_entity: str | None = None
    model_entity_group: str | None = None


@dataclass
class _VariableUsageAccumulator:
    variable_name: str
    request_entity_group: str
    source: VariableSource
    entity_ids: set[str] = field(default_factory=set)
    period_keys: set[str] = field(default_factory=set)
    granularities: set[PeriodGranularity] = field(default_factory=set)
    occurrence_count: int = 0

    def add_entity_periods(
        self, entity_id: str, period_keys: list[Any], granularity: str
    ) -> None:
        self.entity_ids.add(entity_id)
        self.granularities.add(_coerce_granularity(granularity))
        for period_key in period_keys:
            self.period_keys.add(str(period_key))
        self.occurrence_count += max(len(period_keys), 1)

    def add_axis_period(self, period_key: Any | None) -> None:
        if period_key is None:
            self.granularities.add("none")
        else:
            self.period_keys.add(str(period_key))
            self.granularities.add(_period_granularity(period_key))
        self.occurrence_count += 1

    @property
    def period_granularity(self) -> PeriodGranularity:
        granularities = self.granularities or {"none"}
        return (
            next(iter(granularities)) if len(granularities) == 1 else "mixed"
        )


def extract_variable_usage(
    household: dict,
    system,
) -> list[VariableUsageSummary]:
    """Extract grouped variable usage without retaining household values.

    The returned records intentionally exclude request values, entity IDs,
    exact periods, member relationships, and axis bounds. Counts are derived
    while walking the payload, then the underlying identifiers are discarded.
    """
    if not isinstance(household, dict):
        return []

    accumulators: dict[
        tuple[str, str, VariableSource], _VariableUsageAccumulator
    ] = {}

    _extract_entity_group_variables(household, accumulators)
    _extract_axis_variables(household, accumulators)

    return [
        _to_summary(accumulator, system)
        for accumulator in sorted(
            accumulators.values(),
            key=lambda item: (
                item.variable_name,
                item.request_entity_group,
                item.source,
            ),
        )
    ]


def _extract_entity_group_variables(
    household: dict,
    accumulators: dict[
        tuple[str, str, VariableSource], _VariableUsageAccumulator
    ],
) -> None:
    for entity_group, entities in household.items():
        if entity_group == "axes" or not isinstance(entities, dict):
            continue

        for entity_id, variables in entities.items():
            if not isinstance(variables, dict):
                continue

            for variable_name, period_map in variables.items():
                if variable_name in VARIABLE_BLACKLIST:
                    continue

                source = _variable_source(period_map)
                period_keys = (
                    list(period_map.keys())
                    if isinstance(period_map, dict)
                    else []
                )
                granularity = _period_map_granularity(period_keys, period_map)
                accumulator = _get_accumulator(
                    accumulators, variable_name, entity_group, source
                )
                accumulator.add_entity_periods(
                    str(entity_id), period_keys, granularity
                )


def _extract_axis_variables(
    household: dict,
    accumulators: dict[
        tuple[str, str, VariableSource], _VariableUsageAccumulator
    ],
) -> None:
    axes = household.get("axes")
    if not isinstance(axes, list):
        return

    for entry in axes:
        axis_specs = entry if isinstance(entry, list) else [entry]
        for axis in axis_specs:
            if not isinstance(axis, dict):
                continue
            variable_name = axis.get("name")
            if not isinstance(variable_name, str) or variable_name == "":
                continue
            accumulator = _get_accumulator(
                accumulators, variable_name, "axes", "axis"
            )
            accumulator.add_axis_period(axis.get("period"))


def _get_accumulator(
    accumulators: dict[
        tuple[str, str, VariableSource], _VariableUsageAccumulator
    ],
    variable_name: str,
    request_entity_group: str,
    source: VariableSource,
) -> _VariableUsageAccumulator:
    key = (variable_name, request_entity_group, source)
    if key not in accumulators:
        accumulators[key] = _VariableUsageAccumulator(
            variable_name=variable_name,
            request_entity_group=request_entity_group,
            source=source,
        )
    return accumulators[key]


def _to_summary(
    accumulator: _VariableUsageAccumulator,
    system,
) -> VariableUsageSummary:
    variable = getattr(system, "variables", {}).get(accumulator.variable_name)
    if variable is not None:
        availability_status: AvailabilityStatus = "supported"
        model_entity = variable.entity.key
        model_entity_group = variable.entity.plural
    elif accumulator.variable_name in DEPRECATED_VARIABLES:
        availability_status = "deprecated_allowlisted"
        model_entity = None
        model_entity_group = None
    else:
        availability_status = "unsupported"
        model_entity = None
        model_entity_group = None

    return VariableUsageSummary(
        variable_name=accumulator.variable_name,
        request_entity_group=accumulator.request_entity_group,
        source=accumulator.source,
        period_granularity=accumulator.period_granularity,
        entity_count=len(accumulator.entity_ids),
        period_count=len(accumulator.period_keys),
        occurrence_count=accumulator.occurrence_count,
        availability_status=availability_status,
        model_entity=model_entity,
        model_entity_group=model_entity_group,
    )


def _variable_source(period_map: Any) -> VariableSource:
    if not isinstance(period_map, dict):
        return "requested_output" if period_map is None else "household_input"

    values = list(period_map.values())
    if not values:
        return "requested_output"

    has_null = any(value is None for value in values)
    has_non_null = any(value is not None for value in values)
    if has_null and has_non_null:
        return "mixed"
    return "requested_output" if has_null else "household_input"


def _period_map_granularity(
    period_keys: list[Any], period_map: Any
) -> PeriodGranularity:
    if not isinstance(period_map, dict):
        return "unknown"
    if not period_keys:
        return "none"

    granularities = {
        _period_granularity(period_key) for period_key in period_keys
    }
    return next(iter(granularities)) if len(granularities) == 1 else "mixed"


def _period_granularity(period_key: Any) -> PeriodGranularity:
    period = str(period_key)
    if YEAR_RE.match(period):
        return "year"
    if MONTH_RE.match(period):
        return "month"
    if DAY_RE.match(period):
        return "day"
    return "unknown"


def _coerce_granularity(granularity: str) -> PeriodGranularity:
    if granularity in {"year", "month", "day", "mixed", "none"}:
        return granularity
    return "unknown"
