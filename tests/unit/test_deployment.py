import re
import subprocess
from datetime import date
from pathlib import Path

from policyengine_household_api import deployment
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


def test_prewarm_populates_the_cache_the_request_path_reads():
    """Formulas resolve parameters through the root ParameterNode's
    string-keyed at-instant cache; prewarm must land its entries in
    exactly that cache or restored containers still pay the lazy
    full-tree build (issue #1624). Pinned against the real US system
    with an instant outside the prewarm window so other tests cannot
    have populated it."""
    from policyengine_household_api.country import COUNTRIES

    system = COUNTRIES["us"].tax_benefit_system
    instant = "2029-06-01"
    assert instant not in system.parameters._at_instant_cache

    prewarm_parameter_caches(
        tax_benefit_systems={"us": system}, instants=[instant]
    )

    assert instant in system.parameters._at_instant_cache


def test_dockerfile_deployment_imports_reference_real_helpers():
    """Dockerfiles invoke deployment helpers by name inside `python -c`
    strings, which no Python tooling follows: renaming a helper without
    updating them fails only inside the real image build, mid-deploy
    (issue #1625 -- `gcp/cloud_run/worker.Dockerfile` still called
    `snapshot_tax_benefit_systems` after #1623 renamed it, killing the
    failover staging deploy). Pin every such reference to a real
    attribute so the break surfaces in `make test` instead."""
    repo_root = Path(__file__).resolve().parents[2]
    tracked = subprocess.run(
        ["git", "ls-files", "*Dockerfile*"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    assert tracked, "expected at least one tracked Dockerfile"

    referenced = set()
    for relative_path in tracked:
        source = (repo_root / relative_path).read_text()
        for match in re.finditer(
            r"from policyengine_household_api\.deployment import ([\w, ]+)",
            source,
        ):
            for name in match.group(1).split(","):
                referenced.add((relative_path, name.strip()))

    assert referenced, "expected Dockerfiles to import deployment helpers"
    for relative_path, name in sorted(referenced):
        assert hasattr(deployment, name), (
            f"{relative_path} imports `{name}` from "
            "policyengine_household_api.deployment, which no longer "
            "exists -- update the Dockerfile alongside the rename"
        )
