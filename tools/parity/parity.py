"""Golden parity harness for the household API migration.

Captures golden response snapshots from a reference deployment (the live
household API) and diffs any candidate endpoint (e.g. the API v2 household
service) against them, with numeric tolerance. The corpus is seeded from the
real partner payloads in tests/data/customer_households plus synthetic basics.

Usage (from repo root):

    # 1. Freeze goldens against a reference API (local: `make debug` first)
    uv run python tools/parity/parity.py capture --base-url http://localhost:5000

    # 2. Diff a candidate implementation against the goldens
    uv run python tools/parity/parity.py diff --base-url http://localhost:8000

Goldens land in tools/parity/golden/<case>.json with the reference's model
versions recorded; diffs compare `result` deeply (floats: abs 0.01 or rel
1e-6), treat `warnings` as sets, and report model-version drift separately
(a version mismatch explains numeric drift and is flagged, not failed).

Zero third-party deps (stdlib only) so it runs in any environment.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
GOLDEN_DIR = HERE / "golden"
REPO_ROOT = HERE.parent.parent

ABS_TOL = 0.01  # money-scale absolute tolerance
REL_TOL = 1e-6

# Response keys that are run-specific, not contractual.
IGNORED_KEYS = {"computation_tree_uuid"}


def build_corpus() -> dict[str, dict]:
    """Corpus cases: name -> {country, payload}. Seeded from real partner
    households (imported from the test data) plus synthetic basics."""
    sys.path.insert(0, str(REPO_ROOT))
    from tests.data.customer_households import (  # noqa: E402
        amplifi_household,
        amplifi_household_2025,
        impactica_household,
        my_friend_ben_household,
    )

    corpus: dict[str, dict] = {
        "us-my-friend-ben": {"country": "us", "payload": {"household": my_friend_ben_household}},
        "us-amplifi": {"country": "us", "payload": {"household": amplifi_household}},
        "us-amplifi-2025": {"country": "us", "payload": {"household": amplifi_household_2025}},
        "us-impactica": {"country": "us", "payload": {"household": impactica_household}},
        # Synthetic basics — trivially readable cases that catch gross breakage.
        "us-single-adult": {
            "country": "us",
            "payload": {
                "household": {
                    "people": {"adult": {"age": {"2026": 35}, "employment_income": {"2026": 30000}}},
                    "tax_units": {"tu": {"members": ["adult"], "income_tax": {"2026": None}}},
                    "spm_units": {"spm": {"members": ["adult"], "snap": {"2026": None}}},
                    "families": {"fam": {"members": ["adult"]}},
                    "marital_units": {"mu": {"members": ["adult"]}},
                    "households": {"hh": {"members": ["adult"], "state_name": {"2026": "CA"}}},
                }
            },
        },
        "uk-single-adult": {
            "country": "uk",
            "payload": {
                "household": {
                    "people": {"adult": {"age": {"2026": 35}, "employment_income": {"2026": 25000}}},
                    "benunits": {"bu": {"members": ["adult"], "universal_credit": {"2026": None}}},
                    "households": {"hh": {"members": ["adult"], "income_tax": {"2026": None}}},
                }
            },
        },
    }

    # Periphery cases — exercise the validation/warnings layer, not just math.
    corpus["us-warn-partial-month"] = {
        "country": "us",
        "payload": {
            "household": {
                "people": {"adult": {"age": {"2026": 35}, "employment_income": {"2026-01": 2500}}},
                "tax_units": {"tu": {"members": ["adult"], "income_tax": {"2026": None}}},
                "spm_units": {"spm": {"members": ["adult"]}},
                "families": {"fam": {"members": ["adult"]}},
                "marital_units": {"mu": {"members": ["adult"]}},
                "households": {"hh": {"members": ["adult"], "state_name": {"2026": "CA"}}},
            }
        },
    }
    corpus["us-warn-deprecated-input"] = {
        "country": "us",
        "payload": {
            "household": {
                "people": {"adult": {"age": {"2026": 40}, "employment_income": {"2026": 50000},
                                      "medical_out_of_pocket_expenses": {"2026": 1200}}},
                "tax_units": {"tu": {"members": ["adult"], "income_tax": {"2026": None}}},
                "spm_units": {"spm": {"members": ["adult"]}},
                "families": {"fam": {"members": ["adult"]}},
                "marital_units": {"mu": {"members": ["adult"]}},
                "households": {"hh": {"members": ["adult"], "state_name": {"2026": "NY"}}},
            }
        },
    }
    corpus["us-axes-sweep"] = {
        "country": "us",
        "payload": {
            "household": {
                "people": {"adult": {"age": {"2026": 30}, "employment_income": {"2026": None}}},
                "tax_units": {"tu": {"members": ["adult"], "income_tax": {"2026": None}}},
                "spm_units": {"spm": {"members": ["adult"]}},
                "families": {"fam": {"members": ["adult"]}},
                "marital_units": {"mu": {"members": ["adult"]}},
                "households": {"hh": {"members": ["adult"], "state_name": {"2026": "TX"}}},
                "axes": [[{"name": "employment_income", "count": 5, "min": 0, "max": 100000, "period": "2026"}]],
            }
        },
    }

    # Legacy JSON payloads kept in the repo, if present.
    legacy = REPO_ROOT / "tests" / "to_refactor" / "python" / "data"
    for name, country in [("calculate_us_1_data.json", "us"), ("calculate_us_2_data.json", "us")]:
        f = legacy / name
        if f.exists():
            data = json.loads(f.read_text())
            payload = data if "household" in data else {"household": data}
            corpus[f"us-legacy-{name.split('_')[1]}"] = {"country": country, "payload": payload}

    # Per-client cases generated from the analytics inventory, if present.
    cases_dir = HERE / "cases"
    if cases_dir.exists():
        for f in sorted(cases_dir.glob("*.json")):
            data = json.loads(f.read_text())
            corpus[f.stem] = {"country": data["country"], "payload": data["payload"]}

    return corpus


def post(base_url: str, country: str, payload: dict, timeout: int = 120, endpoint: str = "calculate") -> tuple[int, dict]:
    url = f"{base_url.rstrip('/')}/{country}/{endpoint}"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.status, json.loads(res.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {"error": str(e)}


def strip_ignored(obj):
    if isinstance(obj, dict):
        return {k: strip_ignored(v) for k, v in obj.items() if k not in IGNORED_KEYS}
    if isinstance(obj, list):
        return [strip_ignored(v) for v in obj]
    return obj


def numbers_equal(a: float, b: float) -> bool:
    if a == b:
        return True
    return abs(a - b) <= max(ABS_TOL, REL_TOL * max(abs(a), abs(b)))


def deep_diff(golden, candidate, path="") -> list[str]:
    """Structural + numeric diff; returns human-readable difference lines."""
    diffs: list[str] = []
    if isinstance(golden, dict) and isinstance(candidate, dict):
        for k in sorted(set(golden) | set(candidate)):
            p = f"{path}.{k}" if path else k
            if k not in golden:
                diffs.append(f"+ {p} (candidate-only): {json.dumps(candidate[k])[:80]}")
            elif k not in candidate:
                diffs.append(f"- {p} (missing in candidate): {json.dumps(golden[k])[:80]}")
            else:
                diffs.extend(deep_diff(golden[k], candidate[k], p))
    elif isinstance(golden, list) and isinstance(candidate, list):
        if len(golden) != len(candidate):
            diffs.append(f"~ {path}: list length {len(golden)} vs {len(candidate)}")
        for i, (g, c) in enumerate(zip(golden, candidate)):
            diffs.extend(deep_diff(g, c, f"{path}[{i}]"))
    elif isinstance(golden, bool) or isinstance(candidate, bool):
        if golden != candidate:
            diffs.append(f"~ {path}: {golden} vs {candidate}")
    elif isinstance(golden, (int, float)) and isinstance(candidate, (int, float)):
        if not numbers_equal(float(golden), float(candidate)):
            diffs.append(f"~ {path}: {golden} vs {candidate}")
    elif golden != candidate:
        diffs.append(f"~ {path}: {json.dumps(golden)[:60]} vs {json.dumps(candidate)[:60]}")
    return diffs


def cmd_capture(base_url: str, only: str | None, endpoint: str = "calculate", sleep_between: float = 0) -> int:
    import time
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    corpus = build_corpus()
    failures = 0
    for name, case in corpus.items():
        if only and only not in name:
            continue
        if sleep_between:
            time.sleep(sleep_between)
        status, body = post(base_url, case["country"], case["payload"], endpoint=endpoint)
        if status != 200 or body.get("status") != "ok":
            print(f"✗ {name}: HTTP {status} — {json.dumps(body)[:160]}")
            failures += 1
            continue
        snapshot = {
            "case": name,
            "country": case["country"],
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "reference_base_url": base_url,
            "model_versions": body.get("policyengine_bundle") or body.get("model_version"),
            "request": case["payload"],
            "response": strip_ignored(body),
        }
        (GOLDEN_DIR / f"{name}.json").write_text(json.dumps(snapshot, indent=1, sort_keys=True))
        print(f"✓ {name}: golden captured ({len(json.dumps(body))} bytes)")
    print(f"\n{len(list(GOLDEN_DIR.glob('*.json')))} goldens in {GOLDEN_DIR}")
    return 1 if failures else 0


def cmd_diff(base_url: str, only: str | None) -> int:
    goldens = sorted(GOLDEN_DIR.glob("*.json"))
    if not goldens:
        print("No goldens — run capture first.")
        return 2
    total = passed = 0
    for f in goldens:
        snap = json.loads(f.read_text())
        if only and only not in snap["case"]:
            continue
        total += 1
        status, body = post(base_url, snap["country"], snap["request"])
        if status != 200:
            print(f"✗ {snap['case']}: HTTP {status} — {json.dumps(body)[:160]}")
            continue

        golden_versions = snap.get("model_versions")
        cand_versions = body.get("policyengine_bundle") or body.get("model_version")
        version_note = "" if golden_versions == cand_versions else "  [MODEL VERSION DRIFT]"

        diffs = deep_diff(snap["response"].get("result"), strip_ignored(body).get("result"))
        g_warn = set(map(json.dumps, snap["response"].get("warnings") or []))
        c_warn = set(map(json.dumps, body.get("warnings") or []))
        if g_warn != c_warn:
            diffs.append(f"~ warnings: {len(g_warn)} golden vs {len(c_warn)} candidate")

        if not diffs:
            passed += 1
            print(f"✓ {snap['case']}: PARITY{version_note}")
        else:
            print(f"✗ {snap['case']}: {len(diffs)} differences{version_note}")
            for d in diffs[:12]:
                print(f"    {d}")
            if len(diffs) > 12:
                print(f"    … {len(diffs) - 12} more")
    print(f"\n{passed}/{total} cases at parity")
    return 0 if passed == total else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("capture", "diff"):
        p = sub.add_parser(name)
        p.add_argument("--base-url", required=True)
        p.add_argument("--only", help="substring filter on case names")
        p.add_argument("--endpoint", default="calculate", help="calculate | calculate_demo")
        p.add_argument("--sleep-between", type=float, default=0, help="seconds between requests (demo is rate-limited 1/10s)")
    args = ap.parse_args()
    if args.cmd == "capture":
        return cmd_capture(args.base_url, args.only, args.endpoint, args.sleep_between)
    return cmd_diff(args.base_url, args.only)


if __name__ == "__main__":
    raise SystemExit(main())
