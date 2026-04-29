# PolicyEngine Household API 

A version of the PolicyEngine API that runs the `calculate` endpoint over household object. To debug locally, run `make debug`. 

## Quick self-hosted run

If you want to try the API without requesting hosted credentials, run the published Docker image:

```
docker run --rm -p 8080:8080 ghcr.io/policyengine/policyengine-household-api:latest
```

The image can take a little time to initialize on first start and is best run on a machine with roughly
4 GB of RAM available.

Then inspect the service metadata:

```
curl http://localhost:8080/
```

and send calculations to:

```
http://localhost:8080/us/calculate
```

Hosted API docs live at https://www.policyengine.org/us/api.

## Local development with Docker Compose

To run this app locally via Docker Compose:

```
% make docker-build
% make docker-run
```

and point your browser at http://localhost:8080 to access the API.

To develop the code locally, you will want to instead start only the Redis docker container and a one-off
API container, with your local filesystem mounted into the running docker container.

```
% make services-start
% make docker-console
```

Then inside the container, start the Flask service:

```
policyapi@[your-docker-id]:/code$ make debug
```

and point your browser at http://localhost:8080 to access the API.

### Running with other PolicyEngine services

If you're running this alongside other PolicyEngine services (e.g., the main API) and need
containers to communicate across projects, use the external network mode:

```
% make docker-network-create   # Create shared network (once)
% make docker-run-external     # Run with external network
```

This connects the household API to a shared `policyengine-api_default` network that other
PolicyEngine docker-compose projects can also join.

For development with external networking:

```
% make docker-network-create
% make services-start-external
% make docker-console
```

## Period-key conventions

Every input and output on `/calculate` is keyed by a period string. Two shapes
are supported:

- **Year key** — `"2026"`. Treated as the value for the entire year.
- **Month key** — `"2026-01"`. Treated as the value for that single month.

Each PolicyEngine variable has a fixed `definition_period` (year or month).
Annual variables like `employment_income` and `state_name` are defined for
the year; monthly variables like `snap_earned_income`, `snap_gross_income`,
and `rent` are defined for the month.

### Recommended pattern: stay consistent within a request

Pick one cadence per request and use it everywhere:

| You want         | Send inputs as     | Request outputs as     |
| ---------------- | ------------------ | ---------------------- |
| Annual totals    | `{"2026": V}`      | `{"2026": null}`       |
| A specific month | `{"2026-01": V}`   | `{"2026-01": null}`    |

If you only think in yearly amounts, use year keys for everything — including
monthly variables. For numeric inputs, the API treats the year value as the
annual total and distributes it across the 12 months before the engine runs;
the engine returns the annual sum on the way back. Booleans, strings, and
enums are broadcast unchanged across months.

You can also mix a year key with one or more month keys for the same
variable to pin specific months — e.g. `{"2026": 36000, "2026-06": 0}`
means "the annual total is $36k with June pinned to $0; the other 11
months absorb the full $36k." Pinned month values consume part of the
annual total and the remainder is split across the unset months. If
the pinned months sum to more than the annual total, the request is
rejected with a 400 — the budget is inconsistent.

If you need per-month variation without a yearly anchor, key both the
input and the output to the same month.

### What goes wrong when you mix shapes

Sending a single-month input (`{"2026-01": V}`) on a monthly variable but
requesting an annual output (`{"2026": null}`) is the most common pitfall.
The other 11 months default to 0 in the engine, so the annual sum looks like
a year of benefits even though only January was actually specified. The API
returns a `warnings` array in the response when it detects this combination
so you can correct the request before relying on the number.

### What the API echoes back

Output keys are echoed back exactly as you sent them. Input keys are
preserved unchanged; the year-to-month split happens internally and never
shows up in the response.

## Development rules

1. Every endpoint should return a JSON object with at least a "status" and "message" field.

Please note that we do not support branched operations at this time.
