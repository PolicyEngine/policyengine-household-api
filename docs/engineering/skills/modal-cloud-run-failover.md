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
- Open the channel circuit after 3 consecutive Modal probe failures.
- Treat Modal SDK transport/runtime failures and probe timeouts as Modal
  platform failures.
- Do not open the circuit for ordinary Flask response status codes from the
  household API, including app-level 500 responses.
- When the circuit opens, fetch Modal status JSON at most once per minute as
  corroborating evidence; never make that status page a hard dependency.
- Keep probing Modal after failover. Close the circuit only after consecutive
  successful Modal health probes.

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

Do not add App Engine deployment, App Engine traffic promotion, or DNS cutover
to this workflow. Public-domain traffic changes are separate infrastructure
operations.

## Testing Expectations

When changing this system, include focused tests for:

- failover manifest validation and exact-version resolution
- Modal circuit transitions after 3 probe failures
- app-level 4xx/5xx responses not opening the Modal circuit
- Modal platform failures routing to Cloud Run fallback
- `503` fallback exhaustion responses including `Retry-After`
- Modal status JSON being fetched only after elevated local failure evidence
- Cloud Run deploy scripts with stubbed `gcloud`, `docker`, and manifest files
- deployed tests for normal Modal-primary routing and forced Cloud Run fallback
