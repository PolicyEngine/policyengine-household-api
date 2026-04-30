# PolicyEngine Household API

The PolicyEngine Household API computes taxes and benefits for a single household at a single point in time. Send a JSON description of the household, get back a JSON response with the values you asked for.

This guide is for partners integrating the API into user-facing tools — case-management software, eligibility screeners, financial planning calculators, and similar.

## Who this is for

If you maintain software that asks "what would *this specific household* receive in benefits or owe in taxes?", this API is the calculation engine you can call instead of writing those rules yourself. PolicyEngine maintains the rules; you call the endpoint.

This API does not run population-level microsimulations. For "how does this reform affect the country?", see the [PolicyEngine main API](https://policyengine.org/us/api).

## What you can do

- Compute taxes and benefits for any US, UK, Canadian, Israeli, or Nigerian household
- Send inputs annually or month by month, and request outputs at the same cadence
- Get a structured 400 response when the request is malformed, with the specific field that's wrong

## A working example

A family of four in California with $30,000 in annual earnings. Find their SNAP allotment for 2026:

```bash
curl https://household.api.policyengine.org/us/calculate \
  -H "Content-Type: application/json" \
  -d '{
    "household": {
      "people": {
        "parent_1": {"age": {"2026": 35}, "employment_income": {"2026": 30000}},
        "parent_2": {"age": {"2026": 35}},
        "child_1":  {"age": {"2026": 7}},
        "child_2":  {"age": {"2026": 4}}
      },
      "families":   {"family_1":   {"members": ["parent_1","parent_2","child_1","child_2"]}},
      "tax_units":  {"tax_unit_1": {"members": ["parent_1","parent_2","child_1","child_2"]}},
      "households": {"household_1":{"members": ["parent_1","parent_2","child_1","child_2"], "state_name": {"2026": "CA"}}},
      "spm_units":  {"spm_unit_1": {"members": ["parent_1","parent_2","child_1","child_2"], "snap": {"2026": null}}}
    }
  }'
```

Response:

```json
{
  "status": "ok",
  "result": {
    "spm_units": {
      "spm_unit_1": {
        "snap": {"2026": 3924.54}
      }
    }
  }
}
```

The household receives $3,924.54 in SNAP across 2026.

## Endpoints

The hosted API runs at `https://household.api.policyengine.org`. The only endpoint partners use is `/calculate`:

```
POST /{country_id}/calculate
```

Where `country_id` is one of `us`, `uk`, `ca`, `il`, or `ng`. The body is a JSON object with a `household` field (and an optional `policy` field for reform comparisons).

## Self-hosted

If you don't want to depend on the hosted service, run the published Docker image:

```bash
docker run --rm -p 8080:8080 ghcr.io/policyengine/policyengine-household-api:latest
```

The image takes a few seconds to initialize and runs on a machine with roughly 4 GB of RAM. Calculation requests then go to `http://localhost:8080/{country_id}/calculate`.

## Read next

- [Request format](request-format.md) — entities, members, inputs vs outputs
- [Period keys](period-keys.md) — year vs month keys, and what happens when you mix them
- [Response format](response-format.md) — output shape, warnings, error catalog
- [Cookbook](cookbook/index.md) — partner recipes for common workflows
- [Changelog](changelog.md) — what changed and when
