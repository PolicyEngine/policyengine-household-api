# Door 1: Axiom rules under the household API

Status: design and prototype, 2026-11-10. Not run in a deployed Modal app or in
staging. Everything described here is **off by default**: with no Door 1
packages in the image, the worker image definition and every response are
unchanged.

## 1. Goal

"Door 1" is this API with the `policyengine-axiom` provider underneath. The
provider lets Axiom rules answer one PolicyEngine variable at a time: first in
shadow (PolicyEngine answers, Axiom is compared), then in tentative serving
(`compare`), with automatic fallback to PolicyEngine's formula and the
comparison kept running. The first serving channel is `frontier`; `current`
stays plain PolicyEngine.

The host must therefore:

1. bind the provider once per worker, in a way that cannot change `current`;
2. select each request (channel, client) and tell the provider per request;
3. keep every provider problem invisible: PolicyEngine answers instead;
4. offer a kill switch with no redeploy, and value-free monitoring;
5. ship the provider and the rules engine in the worker image without
   disturbing the locked policyengine-us/-core pair.

## 2. The calculation path today (origin/main ebfaa11)

| Step | Where | What matters for Door 1 |
| --- | --- | --- |
| Gateway reads `version` | `libs/household-common/policyengine_household_common/gateway.py:44` | Removes `version` from the body (`current` when absent). |
| Gateway resolves channel | `projects/cloud-run-failover-api/policyengine_household_failover/cloud_run_gateway.py:511`, `manifest.py:145` | An exact package version resolves to the channel that serves it. |
| Worker payload | `gateway.py:74-93` | Carries `modal_routing = {requested_version, resolved_channel}`. |
| Modal dispatch | `worker_dispatch.py:39-65`, `routing_metadata.py:26-41` | The resolved channel reaches Flask as `request.environ["policyengine.resolved_channel"]`. |
| Worker start | `projects/modal-api/policyengine_household_modal/worker_app.py:153-179` | `@modal.enter(snap=True)` imports the Flask app (builds every country system) and prewarms parameter caches into the memory snapshot. |
| After restore | `worker_app.py:181-183` | Re-creates credentials and log threads; threads and sockets do not survive a snapshot. |
| Country systems | `libs/household-api/policyengine_household_api/country.py:540`, `:1103` | One `CountryTaxBenefitSystem()` per country, shared by all requests. |
| Endpoint | `endpoints/household.py:126-267`, `country.calculate` at `:239` | The one call site for `/calculate` and `/calculate_demo`. |
| Reform | `country.py:885-912` (clone at `:898`) | A reform clones the shared system and mutates the clone's parameters. |
| Simulation and response | `country.py:998-1081` | A per-variable exception becomes `null` in the response (`:1074-1079`). |
| Client id | `decorators/analytics.py:176-213` | `sub` of the validated token (`g.authlib_server_oauth2_token`), `@clients` removed. |
| Weekly release | `release_manifest.py:196`; `docs/engineering/skills/modal-release-prs.md` | The old frontier app becomes `current` **without a redeploy**; code-only deploys rebuild both apps from one image definition; `new_app_target: both` makes one app serve both channels. |
| Cloud Run fallback | `cloud_run_worker.py:58-93` | Same Flask app, same routing environ; used when Modal is unavailable. |

### Findings that shape the design

- **F1. Selection must be per request, not per process.** A worker app keeps
  its memory snapshot when the weekly release promotes it from `frontier` to
  `current`, and one app can serve both channels. The gateway already passes
  the resolved channel into each request (table above), so the host can select
  per request at no cost.
- **F2. A second, plain copy of the US system is too expensive.** Measured on
  2026-11-08 (macOS arm64, Python 3.13.3, policyengine-us 2.94.7, core
  3.33.1): building the US system takes 54 s and 1.58 GB; the 72-instant
  prewarm brings it to 3.20 GB; a `clone()` adds 0.83 GB and prewarming the
  clone adds 1.74 GB more (5.78 GB total). Door 1 therefore binds in place,
  into the one shared system, and caps the provider per request.
- **F3. Errors must stay inside the provider.** A variable that raises becomes
  `null` in the response (`country.py:1074-1079`), so the provider must never
  run in `strict` mode here.
- **F4. Modal Volumes do not suit a kill switch.** A running container sees
  another writer's changes only after `Volume.reload()`, which fails while any
  file on the volume is open; concurrent writers to one file lose data ("last
  write wins"). The control therefore lives in a Modal Dict; the outcome counts
  use one directory per container.
- **F5. The host needs a provider that can cap per request.** The adapter
  checks for `runtime.request_context(client_id, mode=...)` and
  `runtime.set_default_request_mode(mode)`; without them it does not bind.

## 3. Design

### 3.1 Bind once per worker, in place

`bind_door1()` runs in the snapshot hook, after the Flask app built the
country systems and **before** `prewarm_parameter_caches()`, so the snapshot
holds the bound system and its prewarmed caches. It:

1. reads `axiom_door1.*` (config file or `AXIOM_DOOR1__*` env vars); when
   `enabled` is false it returns without importing `policyengine_axiom`;
2. refuses `strict` and `off`; accepts `shadow`, `compare`, `on`;
3. checks that the provider has a request-level cap (F5), else does not bind;
4. sets the provider's **process default cap to `off`**, so any calculation
   outside an explicit Door 1 scope gets PolicyEngine's formula (fail closed);
5. calls the provider's `apply_provider(...)` on each configured country
   (default `us`);
6. records which countries have at least one bound variable.

Any exception leaves `bound = False` and the reason in the log.

### 3.2 Select each request

`calculation_scope(country_id)` wraps `country.calculate` in the endpoint and
puts each request of a bound country in one of three tiers, checked in this
order:

| Tier (`axiom_door1` log attribute) | Rule | Request cap passed to `request_context(client_id, mode=...)` | Effect |
| --- | --- | --- | --- |
| `selected` (serving) | Resolved channel in `serve_channels` (default `frontier`), and the client id is listed when `clients` is not empty. | The bind-time mode (`axiom_door1.mode`) | The bind-time mode applies, lowered by the kill switch. |
| `shadow` | Not `selected`, and the resolved channel is in `shadow_channels` (default empty). | `"shadow"` | PolicyEngine answers; Axiom runs and is compared (`shadow` outcome). |
| `unselected` | Everything else, including a request with no channel. | `"off"` | The bound formula calls PolicyEngine's own formula and no Axiom code runs (`unselected` outcome). |

A cap only lowers a binding, never raises one. The serving tier passes the
bind-time mode explicitly, not `mode=None`: inside a request context the
provider reads `mode=None` as "use the process default", which `bind_door1`
sets to `off`. No binding is above the bind-time mode, so this cap lowers
nothing. A request with no client id (`/calculate_demo`) cannot be listed, so
with a client list it lands in `shadow` or `unselected`. The scope never
raises; if entering it fails, the process default (`off`) still applies.

"Shadow for all of `frontier`, serving only for listed clients" is this
configuration:

```yaml
axiom_door1:
  mode: compare
  serve_channels: [frontier]
  clients: [<listed client ids>]
  shadow_channels: [frontier]
```

With `shadow_channels` empty (the default) the behaviour is the two-tier one:
served or off.

Reforms need no host code: the request's reform clones the bound system
(`country.py:898`), and the provider sends any binding whose parameters the
reform changed to PolicyEngine (`reform` outcome).

### 3.3 Keep fallback and errors invisible

| Failure | What the customer gets |
| --- | --- |
| `policyengine-axiom` missing, bad config, bind error, no request cap | PolicyEngine (Door 1 not bound; logged once). |
| A problem with the provider's shipped rules data | PolicyEngine (the provider binds nothing). |
| Engine error in one call | PolicyEngine for that call (`fallback` outcome). |
| Reform touching a bound program | PolicyEngine (`reform` outcome). |
| Request not selected, or outside any scope | PolicyEngine (cap `off`). |
| Kill switch `mode: off` or `deny` | PolicyEngine within about 60 s. |
| Modal unavailable | Cloud Run fallback worker: plain PolicyEngine (no provider). |

The response shape does not change. `policyengine_bundle.model_version` still
names the policyengine-us version.

### 3.4 Image and build

- **Trigger:** the deploy machine sets `HOUSEHOLD_AXIOM_DOOR1_PACKAGES`, a JSON
  list of pip specs (hash-pinned wheel URLs) for the provider and the rules
  engine (`cp313`, Linux x86_64). Unset, the image definition is unchanged (a
  test asserts it).
- **Install:** one `uv_pip_install(*specs, extra_options="--no-deps")` layer
  after the country packages, so the locked policyengine-us/-core pair is never
  replaced. The specs must bring any dependency the lock does not have.
- **Image env:** `AXIOM_DOOR1__ENABLED=true` and `AXIOM_DOOR1__MODE` (from
  `HOUSEHOLD_AXIOM_DOOR1_MODE`, default `shadow`). The selection tiers come
  from `HOUSEHOLD_AXIOM_DOOR1_SERVE_CHANNELS`, `HOUSEHOLD_AXIOM_DOOR1_CLIENTS`
  and `HOUSEHOLD_AXIOM_DOOR1_SHADOW_CHANNELS` (comma-separated; unset keeps
  the config file's value) and become `AXIOM_DOOR1__SERVE_CHANNELS`,
  `AXIOM_DOOR1__CLIENTS` and `AXIOM_DOOR1__SHADOW_CHANNELS`. A channel name
  other than `current` or `frontier` fails the image build, because a
  misspelt channel would select nothing. Listed client ids are then visible
  in the Modal image definition (not in this repository).
- **Rules data:** the provider wheel carries the rules it runs, so
  `axiom_door1.corpus_root` stays empty. A value there overrides it; it must
  name a directory in the image, not on a Volume, because binding runs in the
  snapshot phase.
- **Volume:** a Door 1 image mounts the Volume `household-api-axiom-door1` at
  `/axiom-door1` for outcome counts.
- **Not in the uv lock:** a private dependency in `uv.lock` would break
  `uv sync` for contributors, PR CI and the public Docker image.
- **Cloud Run fallback workers and the public Docker image** do not install
  Door 1 and stay plain PolicyEngine.

No published wheel set exists yet, so no Door 1 image can be built today. The
provider pins one policyengine-us version, so each weekly frontier bump needs
a matching provider wheel (section 5).

### 3.5 The kill switch

- **Source:** Modal Dict `household-api-axiom-door1`, key `control`, one per
  Modal environment: `{"mode": "off|shadow|compare|on", "deny": [...]}`.
  `mode` caps every binding (never raises one); `deny` sends a variable, or
  `program:variable`, to PolicyEngine.
- **In each container:** after restore, a daemon thread copies the Dict into
  `/tmp/axiom-door1-control.json` every 30 s; `PE_AXIOM_CONTROL` points the
  provider at it, which re-reads it every 30 s. Worst case about 60 s.
- **Fail closed at start:** the file starts as `{"mode": "off"}` until the
  first good read, so a kill set before the container started holds even when
  the Dict is unreachable. Later read errors keep the last good control.
- **Operator CLI:**
  `uv run python -m policyengine_household_modal.axiom_door1 --modal-environment main set --mode off --note "..."`;
  `... set --deny snap`; `... show`; `... clear`.

### 3.6 Monitoring

- Per request: the log attribute `axiom_door1`
  (`selected` / `shadow` / `unselected`) in the existing observability
  pipeline.
- Per outcome: the provider counts calls per (client prefix, program,
  variable, outcome), with rows compared, tolerance failures and the largest
  absolute difference. No household values; 8 characters of the client id.
- Sink: each container writes to `/axiom-door1/sink/<MODAL_TASK_ID>/`
  (set after restore, because restored containers share every object built
  before the snapshot), every 300 s and at container exit (`@modal.exit`).
- `stage_finished_days()` merges every container's file per finished UTC day.
  Nothing in this change sends the counts anywhere: any upload is a separate
  job, not built, and a decision for the household API owners (section 7).

### 3.7 Turning it off

1. **Seconds:** kill switch `set --mode off` (or `--deny <variable>`).
2. **One deploy:** deploy without `HOUSEHOLD_AXIOM_DOOR1_PACKAGES` (or with
   `AXIOM_DOOR1__ENABLED=false`). Config is read inside the snapshot, so it
   changes only with a deploy.
3. **Code:** revert the hook commit. It touches one line in the endpoint, the
   worker hooks and the image factory; all new code is in two new modules.

## 4. The change

| Change | Where |
| --- | --- |
| Host adapter: settings, `bind_door1`, `request_tier`, `calculation_scope`, `configure_door1_runtime`, `flush_door1` | `libs/household-api/policyengine_household_api/axiom_door1.py` (new) |
| Endpoint scope | `libs/household-api/policyengine_household_api/endpoints/household.py:239` |
| Config, off by default | `config/default.yaml` (`axiom_door1:`) |
| Bind before prewarm; per-container runtime after restore; flush at exit; volume | `projects/modal-api/policyengine_household_modal/worker_app.py` |
| Optional image layer | `projects/modal-api/policyengine_household_modal/images.py` |
| Modal plumbing: install specs, image env, volume, `ControlMirror`, `start_door1_container_runtime`, `stage_finished_days`, operator CLI | `projects/modal-api/policyengine_household_modal/axiom_door1.py` (new) |
| Tests (73) | `tests/unit/test_axiom_door1.py`, `tests/unit/endpoints/test_household_axiom_door1.py`, `tests/unit/modal_release/test_axiom_door1_modal.py`, fake provider in `tests/fixtures/axiom_door1.py` |

Not built: any upload of the outcome counts, deploy-workflow inputs for the
Door 1 packages, a Door 1 column in the analytics database.

## 5. Rollout (frontier first)

0. **Preconditions:** the household API owners agree and name an owner; a
   hash-pinned wheel set exists for the frontier policyengine-us version.
1. **Merge the hook with Door 1 off.** No image or behaviour change.
2. **Throwaway Modal environment** (the mandatory validation in
   `docs/engineering/skills/modal-images.md`), plus: bind in the snapshot,
   then force a restore (stop the container, dispatch again) to prove the
   engine's native extension survives a memory-snapshot restore; measure
   snapshot memory, restore time and per-request latency in `compare`; flip
   the kill switch and watch the outcome counts change.
3. **Staging, `shadow`:** both channels through the gateway; `current`
   requests must show only `unselected` outcomes.
4. **Production frontier, `shadow`:** a period of live shadow; every
   difference triaged.
5. **Production frontier, `compare`:** only for variables that passed the
   parity gate, first only for listed clients, with the rest of `frontier`
   kept in shadow (section 3.2). Keep `compare` (not `on`) so the comparison
   keeps running.
6. **Wider:** add `current` to `serve_channels` only after a separate
   decision.

The weekly release must never wait for Door 1: if the wheel set does not fit
the new frontier policyengine-us version, deploy that week's app without
Door 1 (PolicyEngine answers) and catch up the next week.

## 6. Risks

1. **Native engine in a memory snapshot.** Unverified. If the extension holds
   threads or handles, restored containers may hang or crash; the deploy's
   `warm_worker` gate exercises the snapshot-creating container, not a restore.
   Fallback: move `bind_door1()` to the after-restore hook (slower cold start).
2. **Memory and cold start** of loaded Axiom programs (not measured).
3. **Latency:** `compare` runs PolicyEngine and Axiom for each bound variable
   of a selected request.
4. **Weekly policyengine-us bumps:** a variable that passed the parity gate
   against one policyengine-us version can differ after PolicyEngine changes
   its formula. `compare` shows the difference.
5. **`--no-deps` install:** the provider runs against whatever
   policyengine-us/-core frontier pins. Import errors leave Door 1 unbound;
   call-time errors fall back per call.
6. **Numbers can flip between requests:** a Modal outage sends frontier
   requests to the plain Cloud Run worker; a kill switch or deny changes
   answers within about 60 s.
7. **Overhead on `current`:** bound variables still pass through the
   provider's wrapper (capped `off`) in an app that was bound as frontier.
8. **Supply chain:** the worker image would pull wheels built outside this
   repository's lock; pin them by hash.
9. **`/calculate_demo`** (public, no client) is selected on `frontier` unless
   `clients` is set.

## 7. Open decisions for the household API owners

- **D1.** Whether this repository hosts Door 1, and who owns it.
- **D2.** On a disagreement beyond tolerance in `compare`, whether the
  customer gets Axiom's number or PolicyEngine's (the second needs a new
  provider mode).
- **D3.** Which traffic is selected: all of `frontier`, a list of consenting
  clients, shadow for all of `frontier` with serving only for listed clients
  (section 3.2), and if and when `current`.
  `calculate_requests.resolved_channel` gives the `frontier` share.
- **D4.** Who holds the kill switch (Modal access) and who is on call.
- **D5.** Whether the value-free outcome counts may leave the host, and how.
- **D6.** Where the provider and engine wheels are hosted, and who builds
  them for each weekly frontier version.
- **D7.** Provenance in the response: unchanged, a response header, or a
  `policyengine_bundle` field.
- **D8.** Analytics: the log attribute only, or a column in
  `calculate_requests` (expand-only migration).
- **D9.** Who approves each variable's step from `shadow` to `compare`.

## 8. Verification (2026-11-10)

- `make format-check` passes. `make test` on Python 3.12: 886 passed,
  1 skipped. The three Door 1 test files: 73 passed.
- Default path: `test_default_config_request_never_touches_the_provider`
  (a default-config `/us/calculate` request never imports the provider),
  `test_disabled_bind_never_imports_policyengine_axiom`,
  `test_worker_image_is_unchanged_without_door1_packages`,
  `test_worker_mounts_no_volume_by_default`.
- Against the real provider and engine, outside this repository (Python 3.14,
  policyengine-us 2.94.7, core 3.33.1), with one variable bound in `compare`,
  `clients=[listed]` and `shadow_channels=[frontier]`: `frontier` with the
  listed client gave `compare`; `frontier` with another client or no client
  gave `shadow`; `current`, no channel and a calculation outside the scope
  gave `unselected`. All seven returned the plain PolicyEngine values.
- Not done: any Modal deploy or staging run, the engine inside a memory
  snapshot, memory and latency measurements, the image layer with real
  wheels, `make test-with-auth`.
