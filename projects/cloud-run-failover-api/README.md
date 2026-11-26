# cloud-run-failover-api

The Cloud Run failover services for the PolicyEngine Household API: the
public gateway (routes to Modal primary with circuit-breaker fallback to
Cloud Run workers) and the fallback workers themselves (which host the same
core household application the Modal workers run, via the `worker` extra).

Never published. The base dependency closure is the slim gateway image —
no country model packages; the worker image adds the core application with
`--extra worker`.

## Per-caller request rate limits

The public gateway rejects over-limit requests with HTTP `429`, JSON code
`rate_limited`, and a `Retry-After` header, before forwarding them to Modal
or a Cloud Run worker. Responses from limited routes carry
`X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset`.
When the request has an `Origin` header, the `429` also allows that origin
to read it, matching the household app's CORS policy.

| Route | Limit | Counted by |
|---|---|---|
| `POST /<country_id>/calculate` | 60 per minute | Auth0 client ID; client IP when the request has no valid token |
| `GET` or `HEAD /analytics/calculate/requests` | 60 per minute | Auth0 client ID; client IP when the request has no valid token |
| `POST /<country_id>/calculate_demo` | 1 per 10 seconds | client IP |

The client ID comes from the same bearer-token validation used for request
logs, so it requires `AUTH0_ADDRESS_NO_DOMAIN` and `AUTH0_AUDIENCE_NO_DOMAIN`.
Counts are kept in each gateway process's memory, so a caller's effective
allowance is the limit multiplied by the number of gateway processes that
receive its requests (Cloud Run instances times Gunicorn workers).

Every request the gateway forwards carries `gateway_rate_limited`, and the
household app skips its own limits for those requests: workers replay every
caller's request from `127.0.0.1`, so the app cannot count callers there.

Configuration (non-secret, passed through `--env-vars-file`):

- `HOUSEHOLD_FAILOVER_RATE_LIMIT_ENABLED`: `true` (default) or `false`. The
  disposable testing deploy sets `false`, because its load test sends every
  request with one client's token.
- `HOUSEHOLD_FAILOVER_TRUSTED_PROXY_COUNT`: how many `X-Forwarded-For` entries,
  counted from the end, were added by proxies in front of the gateway. The
  client IP is the entry at that position; earlier entries come from the
  caller and are ignored. The default `1` matches a request that reaches
  Cloud Run directly. Behind one Google Cloud load balancer, use `2`. `0`
  uses the connection address. With a load balancer in front, also restrict
  gateway ingress to it (`HOUSEHOLD_CLOUD_RUN_GATEWAY_INGRESS`): a caller
  that reaches the `run.app` URL directly controls every entry except the
  last, so a count of `2` would read an address the caller chose. With the
  default `1` behind a load balancer, the client IP read is the load
  balancer's own address, so all callers without a valid token share one
  count.

The release workflow reads both from GitHub Actions variables of the same
names.

## Authenticated caller request logs

When `AUTH0_ADDRESS_NO_DOMAIN` and `AUTH0_AUDIENCE_NO_DOMAIN` are configured,
the public gateway validates an incoming bearer JWT and adds the normalized
Auth0 application client ID to its canonical request completion log as
`auth0_client_id`. Attribution is best effort and never changes routing or the
worker's authoritative authentication decision. The client ID is deliberately
excluded from trace and metric attributes.

For example, find gateway requests for one client in Cloud Logging with:

```text
jsonPayload.service_role="failover_gateway"
jsonPayload.schema_version="policyengine.observability.request.v1"
jsonPayload.auth0_client_id="CLIENT_ID"
```

Those records already contain `request_id`, `status_code`, `duration_ms`,
route, and backend, so future client-specific latency analysis can be built
from logs without adding a high-cardinality metric label.
