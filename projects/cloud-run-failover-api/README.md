# cloud-run-failover-api

The Cloud Run failover services for the PolicyEngine Household API: the
public gateway (routes to Modal primary with circuit-breaker fallback to
Cloud Run workers) and the fallback workers themselves (which host the same
core household application the Modal workers run, via the `worker` extra).

Never published. The base dependency closure is the slim gateway image —
no country model packages; the worker image adds the core application with
`--extra worker`.
