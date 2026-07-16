`/calculate` now validates policy period keys explicitly: every key must
be two dot-separated instants (`"2026-01-01.2026-12-31"`). Malformed keys
return a descriptive 500 — the status the endpoint has always produced
for bad policy input — instead of crashing mid-calculation (core path) or
silently applying the change to a single day (UK wrapper path). The check
runs after household validation, preserving the endpoint's historical
error precedence. Issue #1628 tracks moving this to a 400.
