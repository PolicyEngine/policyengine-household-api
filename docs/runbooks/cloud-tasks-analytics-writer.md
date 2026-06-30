# Cloud Tasks Analytics Writer

This runbook moves calculate analytics writes out of the user-facing request
path. Calculation workers enqueue value-free analytics events to Cloud Tasks;
Cloud Tasks dispatches each event to a private Cloud Run analytics writer,
which persists the existing `visits`, `calculate_requests`, and
`calculate_request_variables` rows.

## One-Time GCP Setup

Do this before deploying with `ANALYTICS__ENABLED=true`. Keep this work outside
CI/CD; the release workflow deploys service revisions, but it must not create
queues, service accounts, or IAM bindings.

1. Enable the Cloud Tasks API in the household API project.
2. Create the queue:

   ```bash
   gcloud tasks queues create analytics-writes \
     --project policyengine-household-api \
     --location us-central1 \
     --max-dispatches-per-second 5 \
     --max-concurrent-dispatches 20 \
     --max-attempts 10 \
     --min-backoff 10s \
     --max-backoff 300s
   ```

3. Provision service accounts:
   - `household-api-worker@policyengine-household-api.iam.gserviceaccount.com`:
     Cloud Run calculation runtime that can enqueue tasks on `analytics-writes`
   - `github-deployment@policyengine-household-api.iam.gserviceaccount.com`
     and `github-deployment-621@policyengine-household-api.iam.gserviceaccount.com`:
     Modal credential accounts that can enqueue tasks on `analytics-writes`
   - `household-analytics-tasks@policyengine-household-api.iam.gserviceaccount.com`:
     Cloud Tasks dispatcher identity
   - `household-api-analytics-writer@policyengine-household-api.iam.gserviceaccount.com`:
     analytics writer runtime that can access Cloud SQL and mounted secrets
4. Grant IAM manually:
   - Modal GCP credentials service account: Cloud Tasks enqueuer on the queue
   - Cloud Run fallback worker service account: Cloud Tasks enqueuer on the queue
   - Modal GCP credentials service account and Cloud Run fallback worker service
     account: Service Account User on
     `household-analytics-tasks@policyengine-household-api.iam.gserviceaccount.com`
     so they can create tasks that ask Cloud Tasks to mint OIDC tokens with
     that dispatcher identity
   - Cloud Tasks service agent: Service Account Token Creator on
     `household-analytics-tasks@policyengine-household-api.iam.gserviceaccount.com`
   - Cloud Tasks dispatcher service account: Cloud Run invoker on the writer.
     Before the writer service exists, grant this at project level; after both
     writer services exist, this can be narrowed to service-level bindings.
   - analytics writer service account: Cloud SQL client and Secret Manager access
5. Configure GitHub environment vars:
   - `HOUSEHOLD_CLOUD_RUN_ANALYTICS_WRITER_SERVICE_ACCOUNT`
   - `ANALYTICS_CLOUD_TASKS_PROJECT`
   - `ANALYTICS_CLOUD_TASKS_LOCATION`
   - `ANALYTICS_CLOUD_TASKS_QUEUE`
   - `ANALYTICS_CLOUD_TASKS_TARGET_URL`
   - `ANALYTICS_CLOUD_TASKS_SERVICE_ACCOUNT_EMAIL`
   - `ANALYTICS_CLOUD_TASKS_OIDC_AUDIENCE`

Manually bootstrap the staging and production writer services before cutting
Modal workers over to Cloud Tasks analytics. The Cloud Run fallback deployment
can derive the writer target URL from the deployed writer service when
`ANALYTICS_CLOUD_TASKS_TARGET_URL` is unset, but Modal workers cannot derive
that value during `modal-sync-secrets.sh`. Modal deploys therefore require a
concrete writer target URL and OIDC audience in the GitHub environment.

After the writer service exists, set `ANALYTICS_CLOUD_TASKS_TARGET_URL` to:

```text
https://WRITER_SERVICE_URL/internal/analytics/calculate/write
```

Set `ANALYTICS_CLOUD_TASKS_OIDC_AUDIENCE` to the writer service base URL.
Cloud Tasks automatically mints a Google OIDC token for
`household-analytics-tasks@policyengine-household-api.iam.gserviceaccount.com`;
it does not mint Auth0 tokens. The writer is therefore protected by private
Cloud Run IAM rather than an in-process Auth0 scope check.

## CI/CD Behavior

When `ANALYTICS__ENABLED=true`,
`.github/scripts/cloud-run-deploy-failover.sh` builds and deploys a dedicated
Cloud Run analytics writer image before fallback workers. It then passes the
writer target URL and Cloud Tasks settings into fallback worker environment
variables. When analytics is disabled, failover deployment skips the writer and
does not require writer service-account or Cloud Tasks configuration. Modal
workers receive the same Cloud Tasks settings through
`.github/scripts/modal-sync-secrets.sh`.

When `ANALYTICS__ENABLED=true`, deploy scripts fail before deployment if the
required Cloud Tasks producer configuration is missing. Runtime analytics
failures do not fail `/calculate`: workers log a warning if analytics context
building or task enqueueing fails, then return the original endpoint response.
The writer returns `500` on persistence failures so Cloud Tasks retries.

The writer service is private (`--no-allow-unauthenticated`). Cloud Run IAM is
the authentication boundary; the Flask writer only validates event shape and
persists analytics.

## Rollout

1. Bootstrap the writer service without changing Modal worker configuration.
2. Confirm `/liveness_check` and `/readiness_check` through authenticated Cloud
   Run access.
3. Create one test task against the writer in staging and confirm it persists a
   single analytics row.
4. Set the staging GitHub environment's Cloud Tasks target URL and OIDC audience
   to the bootstrapped writer service.
5. Deploy staging and send one `/calculate` request. Confirm:
   - Cloud Tasks dispatches one task
   - queue depth returns to zero
   - one analytics row appears with the expected request UUID
   - duplicate dispatch of the same event does not create another row
6. Repeat in production after staging is clean.
