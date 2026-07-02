"""Phase-0 migration inventory: who uses the household API, and how.

Read-only queries against the production user-analytics database (Cloud SQL,
credentials from Secret Manager, IAM via application-default credentials).
Produces the per-client compatibility matrix that drives the API v2 migration:
which clients are active, what countries/versions/endpoints they use, and
which variables they send/request — i.e. what the v2 endpoint must support
before each client can move.

    uv run python tools/parity/inventory.py [--days 90]

Prints a report and writes tools/parity/inventory-report.json.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pymysql
from google.cloud.sql.connector import Connector

HERE = Path(__file__).parent
PROJECT = "policyengine-household-api"


def secret(name: str) -> str:
    return subprocess.run(
        ["gcloud", "secrets", "versions", "access", "latest", f"--secret={name}", f"--project={PROJECT}"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def q(cur, sql: str, params: tuple = ()) -> list[dict]:
    cur.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--secret-prefix", default="household-api-production-")
    args = ap.parse_args()

    pfx = args.secret_prefix
    def psecret(n):
        try:
            return secret(pfx + n)
        except Exception:
            return secret(n)
    import os
    conn_name = os.environ.get("ANALYTICS_CONN") or psecret("USER_ANALYTICS_DB_CONNECTION_NAME")
    connector = Connector()
    conn = connector.connect(
        conn_name,
        "pymysql",
        user=psecret("USER_ANALYTICS_DB_USERNAME"),
        password=psecret("USER_ANALYTICS_DB_PASSWORD"),
        db=None,
    )
    cur = conn.cursor()
    dbs = [r[0] for r in (cur.execute("SHOW DATABASES") or 1) and cur.fetchall()]
    db = next((d for d in dbs if "analytic" in d.lower()), None) or next((d for d in dbs if d not in ("information_schema","mysql","performance_schema","sys")), None)
    print(f"databases: {dbs} -> using {db}")
    cur.execute(f"USE `{db}`")

    report: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_days": args.days,
    }

    # What tables exist (schema drifted across alembic revisions — be flexible)
    tables = [list(r.values())[0] for r in q(cur, "SHOW TABLES")]
    report["tables"] = tables
    print(f"tables: {tables}\n")

    since = f"created_at >= NOW() - INTERVAL {args.days} DAY"
    visits_since = f"datetime >= NOW() - INTERVAL {args.days} DAY"

    if "calculate_requests" in tables:
        report["clients"] = q(cur, f"""
            SELECT client_id,
                   COUNT(*) AS requests,
                   COUNT(DISTINCT country_id) AS countries,
                   GROUP_CONCAT(DISTINCT country_id) AS country_list,
                   GROUP_CONCAT(DISTINCT resolved_channel) AS channels,
                   GROUP_CONCAT(DISTINCT requested_version) AS requested_versions,
                   SUM(response_status_code >= 400) AS error_responses,
                   MIN(created_at) AS first_seen,
                   MAX(created_at) AS last_seen
            FROM calculate_requests
            WHERE {since}
            GROUP BY client_id
            ORDER BY requests DESC
        """)
        report["daily_volume"] = q(cur, f"""
            SELECT DATE(created_at) AS day, COUNT(*) AS requests,
                   COUNT(DISTINCT client_id) AS active_clients
            FROM calculate_requests
            WHERE {since}
            GROUP BY DATE(created_at) ORDER BY day DESC LIMIT 14
        """)
        report["errors_by_client"] = q(cur, f"""
            SELECT client_id, response_status_code, COUNT(*) AS n
            FROM calculate_requests
            WHERE {since} AND response_status_code >= 400
            GROUP BY client_id, response_status_code ORDER BY n DESC LIMIT 20
        """)
        # UK usage specifically (prod UK calc is currently broken — issue #1601)
        report["uk_usage"] = q(cur, f"""
            SELECT client_id, COUNT(*) AS requests, MAX(created_at) AS last_seen,
                   GROUP_CONCAT(DISTINCT response_status_code) AS statuses
            FROM calculate_requests
            WHERE {since} AND country_id = 'uk'
            GROUP BY client_id
        """)

    if "calculate_request_variables" in tables:
        report["variables_by_client"] = q(cur, f"""
            SELECT client_id, variable_name, entity_type, source,
                   period_granularity, availability_status,
                   SUM(occurrence_count) AS n
            FROM calculate_request_variables
            WHERE {since}
            GROUP BY client_id, variable_name, entity_type, source,
                     period_granularity, availability_status
            ORDER BY client_id, n DESC
        """)

    if "visits" in tables:
        report["endpoints"] = q(cur, f"""
            SELECT client_id, endpoint, COUNT(*) AS n, MAX(datetime) AS last_seen
            FROM visits
            WHERE {visits_since}
            GROUP BY client_id, endpoint ORDER BY n DESC LIMIT 40
        """)

    cur.close(); conn.close(); connector.close()

    out = HERE / "inventory-report.json"
    out.write_text(json.dumps(report, indent=1, default=str))

    # Console summary
    print(f"=== Active clients (last {args.days}d) ===")
    for c in report.get("clients", []):
        print(f"  {(c['client_id'] or '(anonymous/demo)')[:24]:26} {c['requests']:>7} req  countries={c['country_list']}  channels={c['channels']}  errors={c['error_responses']}  last={c['last_seen']}")
    print(f"\n=== UK usage (prod UK is broken — who's affected?) ===")
    for c in report.get("uk_usage", []) or [{"client_id": "(none)", "requests": 0, "last_seen": "-", "statuses": "-"}]:
        print(f"  {(c['client_id'] or '(anonymous/demo)')[:24]:26} {c['requests']:>7} req  statuses={c['statuses']}  last={c['last_seen']}")
    print(f"\nFull report: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
