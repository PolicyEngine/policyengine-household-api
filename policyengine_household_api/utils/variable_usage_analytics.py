"""Privacy-safe variable usage extraction for calculate analytics."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

from policyengine_household_api.models.analytics import (
    AvailabilityStatus,
    PeriodGranularity,
    VariableSource,
    VariableUsageSummary,
)
from policyengine_household_api.utils.deprecated_inputs import (
    DEPRECATED_VARIABLES,
)
from policyengine_household_api.utils.household import VARIABLE_BLACKLIST


YEAR_RE = re.compile(r"^\d{4}$")
MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
UNKNOWN_ENTITY_TYPE = "unknown"
MAX_STORED_VARIABLE_NAME_LENGTH = 250
TRUNCATED_VARIABLE_NAME_SUFFIX = "..."


def stored_variable_name(variable_name: str) -> tuple[str, bool]:
    """Return the bounded variable name stored by analytics."""
    if len(variable_name) <= MAX_STORED_VARIABLE_NAME_LENGTH:
        return variable_name, False
    return (
        variable_name[:MAX_STORED_VARIABLE_NAME_LENGTH]
        + TRUNCATED_VARIABLE_NAME_SUFFIX,
        True,
    )


@dataclass
class _VariableUsageAccumulator:
    variable_name: str
    entity_type: str
    source: VariableSource
    entity_ids: set[str] = field(default_factory=set)
    period_keys: set[str] = field(default_factory=set)
    granularities: set[PeriodGranularity] = field(default_factory=set)
    occurrence_count: int = 0

    def add_entity_periods(
        self,
        entity_id: str,
        period_keys: list[Any],
        granularity: str | PeriodGranularity,
    ) -> None:
        self.entity_ids.add(entity_id)
        self.granularities.add(_coerce_granularity(granularity))
        for period_key in period_keys:
            self.period_keys.add(str(period_key))
        self.occurrence_count += max(len(period_keys), 1)

    def add_axis_period(self, period_key: Any | None) -> None:
        if period_key is None:
            self.granularities.add(PeriodGranularity.NONE)
        else:
            self.period_keys.add(str(period_key))
            self.granularities.add(_period_granularity(period_key))
        self.occurrence_count += 1

    @property
    def period_granularity(self) -> PeriodGranularity:
        granularities = self.granularities or {PeriodGranularity.NONE}
        return (
            next(iter(granularities))
            if len(granularities) == 1
            else PeriodGranularity.MIXED
        )


_VariableUsageKey = tuple[str, str, VariableSource]
_VariableUsageAccumulators = dict[_VariableUsageKey, _VariableUsageAccumulator]


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

    entity_type_by_group = _entity_type_by_group(system)
    accumulators: _VariableUsageAccumulators = {}

    _extract_entity_group_variables(
        household,
        system,
        entity_type_by_group,
        accumulators,
    )
    _extract_axis_variables(
        household,
        system,
        entity_type_by_group,
        accumulators,
    )

    return [
        _to_summary(accumulator, system)
        for accumulator in sorted(
            accumulators.values(),
            key=lambda item: (
                item.variable_name,
                item.entity_type,
                item.source,
            ),
        )
    ]


def _extract_entity_group_variables(
    household: dict,
    system,
    entity_type_by_group: dict[str, str],
    accumulators: _VariableUsageAccumulators,
) -> None:
    for entity_group, entities in _iter_household_entity_groups(household):
        for entity_id, variable_name, period_map in _iter_entity_variables(
            entities
        ):
            _add_entity_variable_usage(
                accumulators,
                variable_name,
                entity_group,
                entity_id,
                period_map,
                system,
                entity_type_by_group,
            )


def _iter_household_entity_groups(household: dict):
    for entity_group, entities in household.items():
        if entity_group != "axes" and isinstance(entities, dict):
            yield entity_group, entities


def _iter_entity_variables(entities: dict):
    for entity_id, variables in entities.items():
        if not isinstance(variables, dict):
            continue

        for variable_name, period_map in variables.items():
            if variable_name not in VARIABLE_BLACKLIST:
                yield entity_id, variable_name, period_map


def _add_entity_variable_usage(
    accumulators: _VariableUsageAccumulators,
    variable_name: str,
    entity_group: str,
    entity_id: str,
    period_map: Any,
    system,
    entity_type_by_group: dict[str, str],
) -> None:
    source = _variable_source(period_map)
    period_keys = (
        list(period_map.keys()) if isinstance(period_map, dict) else []
    )
    granularity = _period_map_granularity(period_keys, period_map)
    entity_type = _entity_type_for_variable(
        variable_name,
        entity_group,
        system,
        entity_type_by_group,
    )
    accumulator = _get_accumulator(
        accumulators, variable_name, entity_type, source
    )
    accumulator.add_entity_periods(
        f"{entity_group}\0{entity_id}", period_keys, granularity
    )


def _extract_axis_variables(
    household: dict,
    system,
    entity_type_by_group: dict[str, str],
    accumulators: _VariableUsageAccumulators,
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
            entity_type = _entity_type_for_variable(
                variable_name,
                "axes",
                system,
                entity_type_by_group,
            )
            accumulator = _get_accumulator(
                accumulators,
                variable_name,
                entity_type,
                VariableSource.AXIS,
            )
            accumulator.add_axis_period(axis.get("period"))


def _get_accumulator(
    accumulators: _VariableUsageAccumulators,
    variable_name: str,
    entity_type: str,
    source: VariableSource,
) -> _VariableUsageAccumulator:
    key: _VariableUsageKey = (variable_name, entity_type, source)
    if key not in accumulators:
        accumulators[key] = _VariableUsageAccumulator(
            variable_name=variable_name,
            entity_type=entity_type,
            source=source,
        )
    return accumulators[key]


def _to_summary(
    accumulator: _VariableUsageAccumulator,
    system,
) -> VariableUsageSummary:
    variable = getattr(system, "variables", {}).get(accumulator.variable_name)
    if variable is not None:
        availability_status = AvailabilityStatus.SUPPORTED
    elif accumulator.variable_name in DEPRECATED_VARIABLES:
        availability_status = AvailabilityStatus.DEPRECATED_ALLOWLISTED
    else:
        availability_status = AvailabilityStatus.UNSUPPORTED

    return VariableUsageSummary(
        variable_name=accumulator.variable_name,
        entity_type=accumulator.entity_type,
        source=accumulator.source,
        period_granularity=accumulator.period_granularity,
        entity_count=len(accumulator.entity_ids),
        period_count=len(accumulator.period_keys),
        occurrence_count=accumulator.occurrence_count,
        availability_status=availability_status,
    )


def _entity_type_for_variable(
    variable_name: str,
    request_entity_group: str,
    system,
    entity_type_by_group: dict[str, str],
) -> str:
    variable = getattr(system, "variables", {}).get(variable_name)
    if variable is not None:
        entity_key = getattr(getattr(variable, "entity", None), "key", None)
        if isinstance(entity_key, str) and entity_key:
            return entity_key

    return entity_type_by_group.get(request_entity_group, UNKNOWN_ENTITY_TYPE)


def _entity_type_by_group(system) -> dict[str, str]:
    entity_type_by_group: dict[str, str] = {}
    entities = getattr(system, "entities", []) or []
    if isinstance(entities, dict):
        entities = entities.values()

    for entity in entities:
        entity_key = getattr(entity, "key", None)
        entity_plural = getattr(entity, "plural", None)
        if isinstance(entity_key, str) and entity_key:
            entity_type_by_group[entity_key] = entity_key
        if (
            isinstance(entity_plural, str)
            and entity_plural
            and isinstance(entity_key, str)
            and entity_key
        ):
            entity_type_by_group[entity_plural] = entity_key

    return entity_type_by_group


def _variable_source(period_map: Any) -> VariableSource:
    if not isinstance(period_map, dict):
        return (
            VariableSource.REQUESTED_OUTPUT
            if period_map is None
            else VariableSource.HOUSEHOLD_INPUT
        )

    values = list(period_map.values())
    if not values:
        return VariableSource.REQUESTED_OUTPUT

    has_null = any(value is None for value in values)
    has_non_null = any(value is not None for value in values)
    if has_null and has_non_null:
        return VariableSource.MIXED
    return (
        VariableSource.REQUESTED_OUTPUT
        if has_null
        else VariableSource.HOUSEHOLD_INPUT
    )


def _period_map_granularity(
    period_keys: list[Any], period_map: Any
) -> PeriodGranularity:
    if not isinstance(period_map, dict):
        return PeriodGranularity.UNKNOWN
    if not period_keys:
        return PeriodGranularity.NONE

    granularities = {
        _period_granularity(period_key) for period_key in period_keys
    }
    return (
        next(iter(granularities))
        if len(granularities) == 1
        else PeriodGranularity.MIXED
    )


def _period_granularity(period_key: Any) -> PeriodGranularity:
    period = str(period_key)
    if YEAR_RE.match(period):
        return PeriodGranularity.YEAR
    if MONTH_RE.match(period):
        return PeriodGranularity.MONTH
    if DAY_RE.match(period):
        return PeriodGranularity.DAY
    return PeriodGranularity.UNKNOWN


def _coerce_granularity(
    granularity: str | PeriodGranularity,
) -> PeriodGranularity:
    try:
        return PeriodGranularity(granularity)
    except ValueError:
        return PeriodGranularity.UNKNOWN
