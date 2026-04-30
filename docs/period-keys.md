# Period keys

Every input and output on `/calculate` is keyed by a period string. This page explains how the API treats each shape and what to send for which scenario.

## The two shapes

| Shape  | Example     | Meaning                            |
| ------ | ----------- | ---------------------------------- |
| Year   | `"2026"`    | The value applies to all of 2026   |
| Month  | `"2026-01"` | The value applies to January 2026  |

Each PolicyEngine variable has a fixed `definition_period` of either `"year"` or `"month"`. Annual variables like `employment_income` and `state_name` are defined for the year. Monthly variables like `snap`, `snap_earned_income`, and `rent` are defined for the month.

## Recommended pattern: stay consistent

Pick one cadence per request and use it everywhere:

| Goal             | Send inputs as     | Request outputs as |
| ---------------- | ------------------ | ------------------ |
| Annual totals    | `{"2026": V}`      | `{"2026": null}`   |
| A specific month | `{"2026-01": V}`   | `{"2026-01": null}`|

If you only think in yearly amounts, use year keys for everything — including monthly variables. The API splits or broadcasts year values to each month internally before the engine runs, then returns the annual sum on the way back. Booleans, strings, and enums broadcast unchanged across months.

If you need per-month variation, key both the input and the output to the same months.

## Sending year keys to monthly variables

For a numeric MONTH-defined variable, the API treats the year value as the **annual total** and splits it evenly across the twelve months as `V / 12`.

```jsonc
// $18,000 of annual SNAP earned income →
// $1,500/mo across all twelve months
"snap_earned_income": {"2026": 18000}
```

For boolean, string, and enum MONTH-defined variables, the year value broadcasts unchanged to every month:

```jsonc
// Standard utility allowance = "SUA" all year
"snap_utility_allowance_type": {"2026": "SUA"}
```

This matches the [PolicyEngine main API](https://policyengine.org/us/api) and policyengine-core's `set_input_divide_by_period`.

## Mixing year and month keys for the same variable

You can pin specific months while letting the year value cover the rest. For numeric MONTH-defined variables, the year value is the **budget**: explicit monthly values consume part of it, and the remainder splits evenly across the unset months.

```jsonc
// Annual $18,000 with June pinned to $600.
// Remaining $17,400 splits across the other 11 months
// as $1,581.82/mo.
"snap_earned_income": {
  "2026": 18000,
  "2026-06": 600
}
```

For boolean, string, and enum MONTH-defined variables, explicit monthly values override the year-broadcast for that month, and the year value applies to the rest:

```jsonc
// Standard utility allowance "SUA" all year except
// limited utility allowance "LUA" in June.
"snap_utility_allowance_type": {
  "2026": "SUA",
  "2026-06": "LUA"
}
```

## What the API rejects

The API returns a 400 in two cases.

**Malformed period keys.** Any string that doesn't parse as a year or month:

```jsonc
"snap_earned_income": {"not-a-period": 100}
```

```json
{
  "status": "error",
  "message": "Invalid period key `not-a-period` for `snap_earned_income` on `spm_units/spm_unit_1`. Expected a year (e.g. \"2026\") or a month (e.g. \"2026-01\")."
}
```

**Inconsistent full year.** All twelve months explicit AND the sum disagrees with the annual total:

```jsonc
// Annual $1,200 but monthlies sum to $600 — engine
// can't reconcile this, so the API rejects it.
"snap_earned_income": {
  "2026": 1200,
  "2026-01": 50, "2026-02": 50, "2026-03": 50,
  "2026-04": 50, "2026-05": 50, "2026-06": 50,
  "2026-07": 50, "2026-08": 50, "2026-09": 50,
  "2026-10": 50, "2026-11": 50, "2026-12": 50
}
```

```json
{
  "status": "error",
  "message": "Inconsistent input: monthly values for `snap_earned_income` on `spm_units/spm_unit_1` in 2026 sum to 600, which doesn't match the annual total 1200."
}
```

Partial monthly overrides — any number of explicit months from 0 to 11 — are silently accepted. The remainder is distributed across the unset months even when it's negative.

## Warnings: partial month input + annual output

The most common period-key mistake is sending a single-month input while requesting an annual output:

```jsonc
"snap_earned_income": {"2026-01": 3000},
"snap":               {"2026": null}
```

The other eleven months default to the engine's fallback value (often 0, sometimes a formula-derived default), so the annual SNAP figure looks like a year of benefits even though only January was specified. The response includes a `warnings` array when the API detects this combination:

```json
{
  "status": "ok",
  "warnings": [
    "`snap_earned_income` on `spm_units/spm_unit_1` was keyed for 1 of 12 months in 2026 (2026-01); the remaining 11 months will read the engine's fallback value (often 0, sometimes a formula-derived value), not the value you set. Because an annual output is requested for 2026, those fallback values are summed into the annual total and may not match what you intended. To get an accurate annual figure, either send a yearly key (`{\"2026\": V}`) or set all 12 monthly keys."
  ],
  "result": { "...": "..." }
}
```

The numeric output is unchanged — the warning is informational. Fix it by either sending a year key for the input or setting all twelve months explicitly.

## Output keys

The API echoes your output keys back exactly. If you request `{"2026": null}`, you get `{"2026": <value>}`. If you request `{"2026-06": null}`, you get `{"2026-06": <value>}`. The year-to-month expansion happens internally on inputs and never shows up in the response.

## What's next

- [Response format](response-format.md) — the full response shape and error catalog
- [When does my client lose SNAP this year?](cookbook/eligibility-cliff.md) — the canonical month-keyed recipe
