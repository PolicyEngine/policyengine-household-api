from datetime import date

from policyengine_household_api.deployment import (
    parameter_prewarm_instants,
    prewarm_parameter_caches,
)


class FakeSystem:
    def __init__(self):
        self.instants = []

    def get_parameters_at_instant(self, instant):
        self.instants.append(instant)


def test_parameter_prewarm_instants_span_the_lookback_window():
    """A 2026 request for a monthly variable can demand instants as far
    back as 2023-10 (e.g. co_ccap_fpg_eligible's fiscal-year lookback
    from a 2024 monthly period) and as far forward as 2028-01, so the
    window must cover -3/+2 years of monthly instants (issue #1624)."""
    instants = parameter_prewarm_instants(today=date(2026, 7, 10))

    assert len(instants) == 6 * 12
    assert instants[0] == "2023-01-01"
    assert instants[-1] == "2028-12-01"
    assert "2023-10-01" in instants
    assert "2028-01-01" in instants


def test_parameter_prewarm_instants_are_month_starts():
    instants = parameter_prewarm_instants(today=date(2026, 1, 1))

    assert all(instant.endswith("-01") for instant in instants)
    assert len(set(instants)) == len(instants)


def test_prewarm_parameter_caches_builds_every_instant_on_every_system():
    us = FakeSystem()
    uk = FakeSystem()

    prewarm_parameter_caches(
        tax_benefit_systems={"us": us, "uk": uk},
        instants=["2025-01-01", "2025-02-01"],
    )

    assert us.instants == ["2025-01-01", "2025-02-01"]
    assert uk.instants == ["2025-01-01", "2025-02-01"]


def test_prewarm_parameter_caches_defaults_to_full_window():
    system = FakeSystem()

    prewarm_parameter_caches(tax_benefit_systems={"us": system})

    assert len(system.instants) == len(parameter_prewarm_instants())
