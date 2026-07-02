# Migration plan: household API → policyengine-api-v2

Status as of 2026-07-02. No hard deadline; the strategy is to accumulate
parity evidence slowly until cutover is boring.

## Evidence so far

| Fact | Source |
|---|---|
| 16 client identities, ~43K requests / 90 days | `tools/parity/inventory.py` against prod analytics |
| **100% of traffic is US** — v2 needs US-only parity on day one | inventory |
| `frontier` channel used by 5 clients → version routing is contractual | inventory |
| Prod UK calculate is broken (nobody affected) | #1601 |
| v2 household endpoint (policyengine-api-v2#599) reproduces prod exactly: **5/5 partner payloads at parity, zero drift** at `policyengine-us==1.744.0` | `tools/parity/parity.py` |

## Phases

0. **Inventory** ✅ — per-client compatibility matrix (`inventory-report.json`).
1. **v2 contract** ✅ (experiment) — `projects/policyengine-api-household/` on
   the `household-endpoint-experiment` branch of policyengine-api-v2: sync
   FastAPI `/{country}/calculate`, v1 wire format + envelope, country packages
   as the engine, model version surfaced for pinning.
2. **Golden parity corpus** ✅ — 13 cases: 4 real partner payloads
   (MyFriendBen, Amplifi ×2, Impactica), 2 synthetic basics, 3 periphery
   (partial-month warnings, deprecated input, axes sweep), 5 per-client
   contract cases generated from real variable usage. Goldens frozen from
   production.
3. **Shadow** — run the diff continuously against a deployed v2 staging
   endpoint; regenerate per-client cases as usage evolves.
4. **Pilot** — 1–2 friendly clients (best candidates: the zero-error steady
   clients in the inventory) switch base URL with exact-version pinning.
5. **Cutover** — channel-based policy: `current` served by v2 from date X;
   exact-version pins honored on legacy until date Y. Transparent proxy from
   the old gateway is the zero-client-change fallback.

## Running the tools

```bash
# Client inventory (read-only; prod analytics Cloud SQL via your gcloud ADC)
ANALYTICS_CONN="policyengine-household-api:us-central1:household-api-user-analytics" \
  uv run python tools/parity/inventory.py --days 90

# Regenerate per-client contract cases from the inventory
uv run python tools/parity/corpus_from_inventory.py --top-clients 5

# Freeze goldens from production (unauthenticated demo endpoint, rate-limited)
uv run python tools/parity/parity.py capture \
  --base-url https://household.api.policyengine.org \
  --endpoint calculate_demo --sleep-between 11

# Diff any candidate implementation against the goldens
uv run python tools/parity/parity.py diff --base-url http://127.0.0.1:8080
```

Note: the `USER_ANALYTICS_DB_CONNECTION_NAME` secret points at a stale
instance; the real one is passed via `ANALYTICS_CONN` above.

## Contract decisions taken (revisit before Phase 4)

- **Sync, not job-based** — household calc is sub-second; partners keep
  request/response semantics.
- **Path + envelope preserved** — `/{country}/calculate`, v1 entity structure,
  null-to-compute, `policyengine_bundle.model_version`.
- **Version channels carry over** — v2's Modal registry mirrors
  `current`/`frontier`/exact-pin semantics.

## Known gaps in the v2 experiment (tracked by the periphery corpus cases)

Warnings (partial-month), deprecated-input filtering, axes caps, malformed
period rejection, auth wiring, Modal deploy, analytics. UK support blocked on
#1601's root cause (policyengine-uk 2.x `Simulation` signature).
