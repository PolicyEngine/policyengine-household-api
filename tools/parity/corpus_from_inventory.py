"""Generate per-client parity corpus cases from the analytics inventory.

For each active client, builds a synthetic household that requests that
client's most-used output variables (from calculate_request_variables) on the
entity types they actually use — i.e. an executable statement of "what this
client needs the API to compute." Values are synthetic; variable names,
entities, and states come from real usage, so a case passing parity means the
candidate implementation covers that client's contract.

    uv run python tools/parity/corpus_from_inventory.py [--top-clients 5] [--top-vars 25]

Writes tools/parity/cases/client-<id8>.json; parity.py picks these up
automatically alongside the built-in corpus.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

HERE = Path(__file__).parent
CASES_DIR = HERE / "cases"
REPORT = HERE / "inventory-report.json"

STATE_PREFIXES = {
    "ca_": "CA", "co_": "CO", "ny_": "NY", "tx_": "TX", "il_": "IL",
    "ma_": "MA", "md_": "MD", "mi_": "MI", "nc_": "NC", "nj_": "NJ",
    "or_": "OR", "pa_": "PA", "wa_": "WA", "dc_": "DC", "mo_": "MO",
}

ENTITY_GROUP = {
    "person": None,  # people
    "tax_unit": "tax_units",
    "spm_unit": "spm_units",
    "family": "families",
    "marital_unit": "marital_units",
    "household": "households",
}

YEAR = "2026"


def infer_state(output_vars: list[str]) -> str:
    counts: dict[str, int] = {}
    for v in output_vars:
        for pfx, st in STATE_PREFIXES.items():
            if v.startswith(pfx):
                counts[st] = counts.get(st, 0) + 1
    return max(counts, key=counts.get) if counts else "CA"


def build_case(client_id: str, rows: list[dict], top_vars: int) -> dict:
    outputs = [r for r in rows if r["source"] == "requested_output" and r["availability_status"] == "supported"]
    outputs.sort(key=lambda r: -int(r["n"]))
    chosen = outputs[:top_vars]
    state = infer_state([r["variable_name"] for r in chosen])

    household: dict = {
        "people": {
            "adult": {"age": {YEAR: 35}, "employment_income": {YEAR: 24000}},
            "child": {"age": {YEAR: 6}},
        },
        "tax_units": {"tu": {"members": ["adult", "child"]}},
        "spm_units": {"spm": {"members": ["adult", "child"]}},
        "families": {"fam": {"members": ["adult", "child"]}},
        "marital_units": {"mu": {"members": ["adult"]}},
        "households": {"hh": {"members": ["adult", "child"], "state_name": {YEAR: state}}},
    }

    for r in chosen:
        entity = r["entity_type"]
        # Match the client's real period granularity where it's unambiguous.
        period = f"{YEAR}-01" if r["period_granularity"] == "month" else YEAR
        if entity == "person":
            household["people"]["adult"].setdefault(r["variable_name"], {})[period] = None
        else:
            group = ENTITY_GROUP.get(entity)
            if not group:
                continue
            key = next(iter(household[group]))
            household[group][key].setdefault(r["variable_name"], {})[period] = None

    return {
        "country": "us",
        "payload": {"household": household},
        "meta": {
            "client_id": client_id,
            "state": state,
            "requested_outputs": len(chosen),
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top-clients", type=int, default=5)
    ap.add_argument("--top-vars", type=int, default=25)
    args = ap.parse_args()

    report = json.loads(REPORT.read_text())
    by_client: dict[str, list[dict]] = {}
    for row in report.get("variables_by_client", []):
        if row["client_id"]:
            by_client.setdefault(row["client_id"], []).append(row)

    # Rank clients by request volume from the clients section.
    volume = {c["client_id"]: c["requests"] for c in report.get("clients", []) if c["client_id"]}
    ranked = sorted(by_client, key=lambda c: -volume.get(c, 0))[: args.top_clients]

    CASES_DIR.mkdir(exist_ok=True)
    for client_id in ranked:
        case = build_case(client_id, by_client[client_id], args.top_vars)
        name = f"client-{re.sub(r'[^A-Za-z0-9]', '', client_id)[:8].lower()}"
        (CASES_DIR / f"{name}.json").write_text(json.dumps(case, indent=1))
        print(f"✓ {name}: state={case['meta']['state']} outputs={case['meta']['requested_outputs']} (client {client_id[:12]}…, {volume.get(client_id, '?')} req/90d)")
    print(f"\ncases in {CASES_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
