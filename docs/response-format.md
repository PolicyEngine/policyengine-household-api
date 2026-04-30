# Response format

The `/calculate` endpoint always returns JSON. The shape depends on whether the request succeeded.

## Successful response (200)

```json
{
  "status": "ok",
  "message": null,
  "result": {
    "people": { "...": "..." },
    "families": { "...": "..." },
    "tax_units": { "...": "..." },
    "households": { "...": "..." },
    "spm_units": { "...": "..." }
  },
  "policyengine_bundle": {
    "model_version": "1.634.8",
    "data_version": null,
    "dataset": null
  }
}
```

| Field                 | What it is                                                                 |
| --------------------- | -------------------------------------------------------------------------- |
| `status`              | `"ok"` for any 200 response                                                |
| `message`             | `null` when the request succeeded                                          |
| `result`              | The household payload echoed back, with computed values filling the `null` slots |
| `policyengine_bundle` | The model version used to compute the result                               |

## How outputs come back

The `result` field is the household you sent, with each `null` output slot replaced by the computed value. Output keys match request keys exactly.

**Request:**
```json
"spm_units": {
  "spm_unit_1": {
    "snap": {"2026": null}
  }
}
```

**Response:**
```json
"spm_units": {
  "spm_unit_1": {
    "snap": {"2026": 3924.54}
  }
}
```

If you request a per-month breakdown, you get a per-month breakdown:

```json
"snap": {
  "2026-01": 276.10,
  "2026-02": 276.10,
  "2026-03": 276.10,
  "...": "..."
}
```

## The `warnings` array

When the API detects a request shape that may produce surprising numbers, it adds a `warnings` field alongside `result`. The numeric output is unchanged — warnings are advisory.

The most common trigger is a partial monthly input paired with an annual output for the same year:

```json
{
  "status": "ok",
  "warnings": [
    "`snap_earned_income` on `spm_units/spm_unit_1` was keyed for 1 of 12 months in 2026 (2026-01); the remaining 11 months will read the engine's fallback value..."
  ],
  "result": { "...": "..." }
}
```

See [Period keys](period-keys.md#warnings-partial-month-input-annual-output) for the full list of cases that arm a warning and how to fix them.

The `warnings` field is omitted entirely when there are no warnings. It's safe to check `if "warnings" in body:` rather than testing for an empty array.

## Error responses (400)

A 400 means the request was rejected before the engine ran. The body always includes `status: "error"` and a human-readable `message`:

```json
{
  "status": "error",
  "message": "<description of what's wrong>"
}
```

The endpoint catches malformed payloads early so partners can fix the request without burning a calculation. Common 400 cases:

| Trigger                                                  | `message` includes                          |
| -------------------------------------------------------- | ------------------------------------------- |
| Missing required entity (e.g. no `tax_units`)            | `"Invalid household payload"` + Pydantic detail |
| Unknown variable name                                    | Pydantic validation error                   |
| Unparseable period key like `"not-a-period"` or `"2026/13"` | `"Invalid period key"` + variable name      |
| All twelve months explicit AND sum ≠ annual total        | `"Inconsistent input"` + variable name      |
| `axes` exceeds 10 entries or count > 100                 | `"'axes' may contain at most..."`            |

## Error responses (500)

A 500 means the engine raised an exception during calculation. The body has the same shape as a 400, but the message starts with `"Error calculating household under policy:"`:

```json
{
  "status": "error",
  "message": "Error calculating household under policy: <exception detail>"
}
```

500s usually indicate an inconsistency in the household that the upfront validators couldn't catch — for example, a person referenced in `members` that doesn't exist in `people`, or a variable whose computation hit an unexpected divide-by-zero. File an issue at [github.com/PolicyEngine/policyengine-household-api/issues](https://github.com/PolicyEngine/policyengine-household-api/issues) with the request body if you hit one.

## Error responses (404)

A 404 means the country ID isn't recognized:

```json
{
  "status": "error",
  "message": "Country `xyz` not found."
}
```

Supported country IDs are `us`, `uk`, `ca`, `il`, and `ng`.

## What's next

- [Cookbook](cookbook/index.md) — see warnings and errors in action
- [Changelog](changelog.md) — when error catalog entries were added or changed
