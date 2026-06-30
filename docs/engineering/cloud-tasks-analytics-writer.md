# Cloud Tasks Analytics Writer Architecture

The Cloud Tasks analytics writer moves calculate analytics persistence out of
the user-facing `/calculate` response path. Household API workers still observe
requests and build value-free analytics metadata, but they enqueue that metadata
to Cloud Tasks instead of writing directly to the analytics database.

Cloud Tasks then dispatches the event to a private Cloud Run writer. The writer
validates the event and persists the existing analytics tables:

- `visits`
- `calculate_requests`
- `calculate_request_variables`

## Purpose

The original analytics path made the Household API request wait for database
persistence. That created three concerns:

- User-facing latency included analytics database write time.
- Analytics database failures could affect `/calculate` reliability.
- Retrying analytics writes was difficult to do cleanly from a synchronous API
  request.

The async writer separates request handling from persistence. The API remains
responsible for deciding what should be observed. The writer is responsible for
storing that observation and letting Cloud Tasks retry transient write failures.

## Request Flow

1. A Modal or Cloud Run household worker receives a `/calculate` request.
2. The Household API builds an `AnalyticsContext` before running the endpoint.
3. The calculate endpoint runs normally.
4. After the endpoint returns, the worker enqueues a Cloud Tasks HTTP task with
   the analytics event and response status code.
5. Cloud Tasks calls the private writer endpoint with a Google OIDC token.
6. The writer validates the event schema and persists analytics rows.
7. If persistence fails, the writer returns `500` so Cloud Tasks can retry.

Analytics is best-effort from the user's point of view. If analytics context
building or Cloud Tasks enqueueing fails, the worker logs the failure and returns
the original `/calculate` response.

## Service Responsibilities

The Household API worker:

- Checks whether analytics is enabled.
- Builds value-free request metadata.
- Extracts grouped variable usage metadata from the request shape.
- Enqueues a Cloud Tasks event after `/calculate` completes.
- Never fails a successful calculation because analytics enqueueing failed.

The Cloud Tasks queue:

- Holds pending analytics write events.
- Authenticates writer calls with a Google OIDC token.
- Retries writer calls that return retryable failures.

The Cloud Run writer:

- Accepts only analytics write events.
- Validates the event schema.
- Writes analytics rows to the analytics database.
- Returns `400` for invalid events.
- Returns `500` for persistence failures so Cloud Tasks retries.

The writer does not run calculations, expose the public Household API, serve the
analytics read endpoint, or load country packages as part of normal operation.

## Setup Model

This feature requires infrastructure outside the Python application:

- A Cloud Tasks queue.
- Producer permissions for each runtime that can serve `/calculate`.
- A dispatcher identity that Cloud Tasks uses for OIDC-authenticated calls.
- A private Cloud Run writer service.
- Analytics database credentials for the writer.

The deploy scripts deploy service revisions and pass runtime configuration. They
do not create queues, service accounts, IAM bindings, or database resources.
Those are intentional one-time infrastructure responsibilities.

When analytics is enabled, each calculation runtime needs enough configuration
to enqueue Cloud Tasks events. The writer needs enough configuration to connect
to the analytics database. When analytics is disabled, calculation runtimes
should not receive Cloud Tasks configuration or analytics database credentials.

## Critical Concerns

The writer is private. Cloud Run IAM is the authentication boundary, and Cloud
Tasks authenticates by minting a Google OIDC token for the dispatcher identity.
The Flask writer validates event shape, but it does not perform Auth0
authorization.

Cloud Tasks may deliver the same event more than once. Duplicate delivery must
be safe. The task identity and persisted request UUID are used to avoid duplicate
calculate request rows.

Analytics data must remain value-free. The event stores metadata and grouped
variable usage only. It must not store household values, entity IDs, exact member
relationships, or enough period detail to reconstruct a household payload.

Database schema readiness is still a release concern. Migrations must run before
the writer receives traffic, and the writer should fail loudly if the analytics
schema is not ready.

## System Constraints

This is still part of the Household API system. It is not an independent
analytics product with a separate release process, schema ownership model, or
public API contract.

Analytics request capture is still part of the main Household API service.
Workers still do a small amount of request-path analytics work: checking config,
building context, extracting value-free variable usage metadata, and enqueueing
the task. Only database persistence moves off the request path.

The public analytics read endpoint remains on the main Household API service.
The writer only handles asynchronous persistence.

Every runtime that can serve `/calculate` must be able to enqueue analytics tasks
when analytics is enabled. This includes Modal workers and Cloud Run fallback
workers.

The writer image is intentionally smaller than calculation worker images. It
should avoid importing country packages or calculation code unless persistence
starts requiring them.

## Related Operations

Environment-specific queue names, service account identities, IAM commands,
writer URLs, and rollout smoke-test steps belong in the operational runbook, not
in this architecture note. See `docs/runbooks/cloud-tasks-analytics-writer.md`.
