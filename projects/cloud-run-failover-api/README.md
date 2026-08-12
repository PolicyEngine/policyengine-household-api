# cloud-run-failover-api

The Cloud Run failover services for the PolicyEngine Household API: the
public gateway (routes to Modal primary with circuit-breaker fallback to
Cloud Run workers) and the fallback workers themselves (which host the same
core household application the Modal workers run, via the `worker` extra).

Never published. The base dependency closure is the slim gateway image —
no country model packages; the worker image adds the core application with
`--extra worker`.

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
