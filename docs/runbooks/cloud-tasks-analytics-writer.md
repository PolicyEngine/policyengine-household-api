# Cloud Tasks Analytics Writer Runbook

This runbook covers the operational setup for moving calculate analytics writes
out of the user-facing request path. Calculation workers enqueue value-free
analytics events to Cloud Tasks; Cloud Tasks dispatches each event to a private
Cloud Run analytics writer, which persists the existing `visits`,
`calculate_requests`, and `calculate_request_variables` rows.

Keep environment-specific identifiers in the deployment environment or internal
infrastructure records, not in this repository. Examples below use placeholders
such as `<PROJECT_ID>` and `<ANALYTICS_QUEUE_NAME>`.

## One-Time GCP Setup

Do this before deploying with `ANALYTICS__ENABLED=true`. Keep this work outside
CI/CD; the release workflow deploys service revisions, but it must not create
queues, service accounts, or IAM bindings.

1. Enable the Cloud Tasks API in the target GCP project.
2. Create a Cloud Tasks queue for analytics writes:

   ```bash
   gcloud tasks queues create <ANALYTICS_QUEUE_NAME> \
     --project <PROJECT_ID> \
     --location <REGION> \
     --max-dispatches-per-second <DISPATCHES_PER_SECOND> \
     --max-concurrent-dispatches <MAX_CONCURRENT_DISPATCHES> \
     --max-attempts <MAX_ATTEMPTS> \
     --min-backoff <MIN_BACKOFF> \
     --max-backoff <MAX_BACKOFF>
   ```

3. Provision runtime identities for:

   - Modal workers that can serve `/calculate`.
   - Cloud Run fallback workers that can serve `/calculate`.
   - The Cloud Tasks dispatcher identity used for writer OIDC tokens.
   - The Cloud Run analytics writer runtime.

4. Grant IAM manually, using the narrowest scope available:

   - Modal worker producer identity: Cloud Tasks enqueuer on the analytics queue.
   - Cloud Run fallback worker identity: Cloud Tasks enqueuer on the analytics
     queue.
   - Modal and Cloud Run producer identities: Service Account User on the Cloud
     Tasks dispatcher identity, so they can create tasks that ask Cloud Tasks to
     mint OIDC tokens with that dispatcher identity.
   - Cloud Tasks service agent: Service Account Token Creator on the dispatcher
     identity.
   - Cloud Tasks dispatcher identity: Cloud Run invoker on the analytics writer
     service.
   - Analytics writer runtime identity: Cloud SQL client and access to only the
     secrets required to connect to the analytics database.

   Avoid broad project-level grants where service-level or queue-level grants are
   available. If bootstrap ordering forces a temporary broad grant, remove it
   after the writer service exists and replace it with a narrow binding.

5. Configure GitHub environment vars:

   - `HOUSEHOLD_CLOUD_RUN_ANALYTICS_WRITER_SERVICE_ACCOUNT`
   - `ANALYTICS_CLOUD_TASKS_PROJECT`
   - `ANALYTICS_CLOUD_TASKS_LOCATION`
   - `ANALYTICS_CLOUD_TASKS_QUEUE`
   - `ANALYTICS_CLOUD_TASKS_TARGET_URL`
   - `ANALYTICS_CLOUD_TASKS_SERVICE_ACCOUNT_EMAIL`
   - `ANALYTICS_CLOUD_TASKS_OIDC_AUDIENCE`

## Writer URL Configuration

Bootstrap the writer service before cutting Modal workers over to Cloud Tasks
analytics. The Cloud Run fallback deployment can derive the writer target URL
from the deployed writer service when `ANALYTICS_CLOUD_TASKS_TARGET_URL` is
unset, but Modal workers cannot derive that value during `modal-sync-secrets.sh`.
Modal deploys therefore require a concrete writer target URL and OIDC audience
in the GitHub environment.

After the writer service exists, set `ANALYTICS_CLOUD_TASKS_TARGET_URL` to the
writer endpoint:

```text
<WRITER_SERVICE_BASE_URL>/internal/analytics/calculate/write
```

Set `ANALYTICS_CLOUD_TASKS_OIDC_AUDIENCE` to the writer service base URL. Cloud
Tasks automatically mints a Google OIDC token for the configured dispatcher
identity; it does not mint Auth0 tokens. The writer is therefore protected by
private Cloud Run IAM rather than an in-process Auth0 scope check.

## CI/CD Behavior

When `ANALYTICS__ENABLED=true`,
`.github/scripts/cloud-run-deploy-failover.sh` builds and deploys a dedicated
Cloud Run analytics writer image before fallback workers. It then passes the
writer target URL and Cloud Tasks settings into fallback worker environment
variables.

When analytics is disabled, failover deployment skips the writer and does not
require writer service-account, Cloud Tasks configuration, or analytics database
credentials. Modal secret sync follows the same rule: analytics-specific values
are only included when analytics is enabled.

When `ANALYTICS__ENABLED=true`, deploy scripts fail before deployment if the
required Cloud Tasks producer configuration is missing. Runtime analytics
failures do not fail `/calculate`: workers log a warning if analytics context
building or task enqueueing fails, then return the original endpoint response.
The writer returns `500` on persistence failures so Cloud Tasks retries.

The writer service is private (`--no-allow-unauthenticated`). Cloud Run IAM is
the authentication boundary; the Flask writer only validates event shape and
persists analytics.

## Rollout

The release workflow deploys staging and production in a single run: a push to
`main` deploys Modal and Cloud Run staging, runs the deployed integration
tests, and then deploys production in the same workflow run. There is no
staging-only release trigger, so a merge activates both environments minutes
apart. Analytics enqueue failures do not fail `/calculate` or the integration
tests, so a broken analytics path will not stop the pipeline; the row-level
checks below are the only verification that analytics still flow.

1. Before merging, bootstrap the writer service without changing Modal worker
   configuration.
2. Confirm `/liveness_check` and `/readiness_check` through authenticated Cloud
   Run access.
3. Create one test task against the writer in a non-production environment and
   confirm it persists a single analytics row.
4. Set each GitHub environment's Cloud Tasks target URL and OIDC audience to
   that environment's bootstrapped writer service. Configure both the staging
   and production GitHub environments before merging, because one merge
   deploys both.
5. Promptly after the merge's deploy run completes, send one `/calculate`
   request to staging and one to production. For each environment, confirm:
   - Cloud Tasks dispatches one task.
   - Queue depth returns to zero.
   - One analytics row appears with the expected request UUID.
   - Duplicate dispatch of the same event does not create another calculate
     request row.

## Security Checklist

- Do not commit project IDs, service account emails, writer URLs, database
  credentials, or secret names to this file.
- Store exact infrastructure identifiers in protected deployment environment
  configuration or internal infrastructure records.
- Keep the writer private and unauthenticated to the public internet.
- Keep Cloud Tasks producer permissions limited to runtimes that serve
  `/calculate`.
- Keep writer database permissions limited to analytics persistence.
- Verify analytics stays value-free before adding fields to the event payload.
