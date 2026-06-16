# Modal Cloud Run Failover

Use this guidance when changing the Cloud Run gateway, Cloud Run fallback
workers, failover manifest, or GitHub Actions steps that keep Modal as primary
and Cloud Run as fallback.

## Architecture

Production traffic should enter through the Cloud Run gateway. The gateway
routes to Modal `current` and `frontier` workers while Modal is healthy. If
the Modal circuit for a channel opens, the gateway routes that channel to the
matching private Cloud Run fallback worker.

Cloud Run fallback workers are deployed for both active channels but use
`min-instances=0`. The Cloud Run gateway uses `min-instances=1`.

The fallback manifest is separate from the strict Modal release manifest and is
stored in GCS. It records each active channel's Modal worker app name, Cloud
Run worker URL, package versions, and analytics migration metadata. The Cloud
Run gateway must be able to resolve `current`, `frontier`, and exact US/UK
package version requests without reading Modal state at request time.

## Health And Failover

Do not poll Modal's public status page during normal healthy operation. The
gateway should check `https://status.modal.com/index.json` only after local
Modal failure evidence opens or is about to open the circuit.

Use this circuit policy unless a PR explicitly changes it:

- Probe active Modal workers directly by channel.
- Treat a channel as a fallback candidate after elevated local Modal failure
  evidence crosses the configured sliding-window threshold. Defaults are 10
  Modal failures, a 50% failure rate, and a 60-second window.
- Open the channel circuit only when the independent Modal canary also fails.
- Deploy the Modal canary with the Modal release pathway. It must stay tiny:
  no household API imports, country packages, Cloud SQL, GCS, Auth0,
  analytics, or secrets.
- Keep Modal request and probe timeouts separate. Request timeouts should be
  long enough for healthy but loaded calculations; probe timeouts should stay
  short so recovery checks do not consume request capacity.
- Do not open the circuit for ordinary Flask response status codes from the
  household API, including app-level 500 responses.
- When local failure evidence crosses the threshold or the circuit opens, fetch
  Modal status JSON at most once per minute as corroborating evidence; never
  make that status page a hard dependency.
- Keep probing Modal after failover. Close the circuit only after the minimum
  open window elapses and repeated recovery checks pass. A recovery check must
  pass both the independent Modal canary and the channel's direct Modal worker
  health probe.

When neither Modal nor the Cloud Run fallback worker can serve a request, the
gateway returns HTTP `503 Service Unavailable`, includes `Retry-After: 10`,
and returns JSON with code `backend_unavailable`. Do not invent custom HTTP
status codes such as 529.

## Deployment Workflow

Mirror the existing staged Modal release pathway:

1. Run the existing lint and test jobs.
2. Resolve Modal release config.
3. Deploy the Modal app set to staging.
4. Deploy staging Cloud Run fallback workers and gateway from the active Modal
   staging manifest.
5. Run deployed tests against both the Modal gateway and the Cloud Run gateway.
6. Deploy the Modal app set to production.
7. Deploy production Cloud Run fallback workers and gateway from the active
   Modal production manifest.
8. Smoke-check production Cloud Run gateway health.

Stop retired Modal worker apps only after the corresponding Cloud Run failover
manifest has been refreshed (after steps 4 and 7), not during the Modal deploy.
Stopping them earlier would leave the failover gateway's stored GCS manifest
pointing a channel at a stopped Modal app until the Cloud Run deploy refreshes
it. The release workflow enforces this by setting `HOUSEHOLD_DEFER_MODAL_CLEANUP`
on the Modal deploy jobs and running cleanup in dedicated
`cleanup-modal-staging` and `cleanup-modal-production` jobs that depend on the
matching Cloud Run deploy.

Do not add App Engine deployment, App Engine traffic promotion, or DNS cutover
to this workflow. Public-domain traffic changes are separate infrastructure
operations.

The Cloud Run deploy wrapper is
`.github/scripts/cloud-run-deploy-failover.sh`. It reads Modal channel
metadata through `.github/scripts/cloud_run_failover_channels.py`, deploys
private `current` and `frontier` Cloud Run workers with `min-instances=0`,
uploads the GCS failover manifest, then deploys the public gateway with
`min-instances=1`.

Default Cloud Run concurrency should support at least 25 concurrent household
requests. Keep gateway container workers, gateway Cloud Run concurrency,
worker container threads, and worker Cloud Run concurrency aligned; otherwise
Cloud Run may send more concurrent requests to a container than Gunicorn can
serve. Load-test at least 25 concurrent requests through the Cloud Run gateway
before DNS cutover or any production traffic migration. Use
`.github/scripts/cloud_run_gateway_load_test.py` against the deployed gateway
URL for this pre-cutover check. For a local isolated testing deployment, use
`.github/scripts/cloud-run-testing-deploy-and-load-test.sh`; it deploys a
testing namespace, smoke-checks the gateway, and runs the load-test harness.

Do not recursively `chown` the Cloud Run worker virtualenv at `/opt/venv`.
The runtime user only needs read and execute access to run Python and installed
console scripts. Keep `/opt/venv` root-owned, set `PYTHONDONTWRITEBYTECODE=1`,
and only `chown` paths the app must write to. Recursive ownership rewrites over
the worker virtualenv are very slow in Docker Desktop because the venv contains
tens of thousands of files.

Pass non-secret Cloud Run configuration with `--env-vars-file`. Sync secret
values to Secret Manager and bind them with `--set-secrets`; do not pass raw
secret values through `--set-env-vars` or delimiter-joined command arguments.

IAM is one-time infrastructure setup and must stay outside the release
workflow. The Cloud Run deploy wrapper should not call
`add-iam-policy-binding` or otherwise grant roles. Configure these bindings
through one-time setup or IaC before deployment:

- the GitHub deployment service account needs `roles/storage.objectAdmin` on
  the manifest bucket so the workflow can upload manifests
- the gateway runtime service account needs `roles/storage.objectViewer` on
  the manifest bucket so runtime manifest reads work with least privilege
- gateway and worker runtime service accounts need
  `roles/secretmanager.secretAccessor` on the Secret Manager secrets they mount
- the gateway runtime service account needs `roles/run.invoker` on the private
  worker services it calls
- the worker runtime service account needs `roles/cloudsql.client` so it can
  reach the analytics database through the Cloud SQL Python connector

The deploy wrapper requires `HOUSEHOLD_CLOUD_RUN_GATEWAY_SERVICE_ACCOUNT` and
`HOUSEHOLD_CLOUD_RUN_WORKER_SERVICE_ACCOUNT`; it does not fall back to the
Compute Engine default service account, so a public deploy fails loudly when a
provisioned runtime service account is missing. The disposable testing deploy
script may default these to the compute SA for throwaway namespaces.

The release workflow should deploy images, services, secret versions, and
manifests; it should not mutate IAM on every run.

## Testing Expectations

When changing this system, include focused tests for:

- failover manifest validation and exact-version resolution
- Modal circuit candidate transitions after the sliding-window threshold
- Modal canary failure being required before fallback opens
- Modal canary success preventing fallback even after the threshold is crossed
- open-circuit recovery requiring repeated canary and Modal worker health
  successes
- app-level 4xx/5xx responses not opening the Modal circuit
- Modal platform failures routing to Cloud Run fallback
- `503` fallback exhaustion responses including `Retry-After`
- Modal status JSON being fetched only after elevated local failure evidence
- Cloud Run deploy scripts with stubbed `gcloud`, `docker`, and manifest files
- deployed tests for normal Modal-primary routing and forced Cloud Run fallback
- a 25-concurrent-request load test against the Cloud Run gateway before any
  production traffic cutover
