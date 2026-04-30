# When will I lose SNAP this year?

Find the month in which SNAP eligibility ends after a mid-year income change — in a single API call, with no extra round trips.

This recipe uses month-keyed inputs for a variable that changes month over month (`snap_earned_income`) and month-keyed outputs for the variable you want to track (`snap`). The response gives back twelve monthly SNAP figures, and the first month with `0` is the cliff.

## What you'll learn

- How to send a different value for each month of the same variable
- How to request twelve monthly outputs in one request
- How to read the response to find a benefit cliff

## The household

A family of four in California: two adults and two children. One adult earns $1,500 per month from January through May, then takes a higher-paying job and earns $2,000 per month from June through December.

| Period            | Gross earnings | Annual to date |
| ----------------- | -------------- | -------------- |
| Jan–May (5 mo)    | $1,500/mo      | $7,500         |
| Jun–Dec (7 mo)    | $2,000/mo      | $21,500        |
| Full year         | —              | $21,500        |

## The request

=== "curl"

    ```bash
    curl https://household.api.policyengine.org/us/calculate \
      -H "Content-Type: application/json" \
      -d @- <<'JSON'
    {
      "household": {
        "people": {
          "parent_1": {"age": {"2026": 35}},
          "parent_2": {"age": {"2026": 35}},
          "child_1":  {"age": {"2026": 7}},
          "child_2":  {"age": {"2026": 4}}
        },
        "families": {
          "family_1": {
            "members": ["parent_1", "parent_2", "child_1", "child_2"]
          }
        },
        "tax_units": {
          "tax_unit_1": {
            "members": ["parent_1", "parent_2", "child_1", "child_2"]
          }
        },
        "households": {
          "household_1": {
            "members": ["parent_1", "parent_2", "child_1", "child_2"],
            "state_name": {"2026": "CA"}
          }
        },
        "spm_units": {
          "spm_unit_1": {
            "members": ["parent_1", "parent_2", "child_1", "child_2"],
            "snap_earned_income": {
              "2026-01": 1500, "2026-02": 1500, "2026-03": 1500,
              "2026-04": 1500, "2026-05": 1500,
              "2026-06": 2000, "2026-07": 2000, "2026-08": 2000,
              "2026-09": 2000, "2026-10": 2000, "2026-11": 2000,
              "2026-12": 2000
            },
            "snap": {
              "2026-01": null, "2026-02": null, "2026-03": null,
              "2026-04": null, "2026-05": null, "2026-06": null,
              "2026-07": null, "2026-08": null, "2026-09": null,
              "2026-10": null, "2026-11": null, "2026-12": null
            }
          }
        }
      }
    }
    JSON
    ```

=== "Python"

    ```python
    import requests

    months = [f"2026-{m:02d}" for m in range(1, 13)]
    earnings = {m: (1500 if int(m[-2:]) <= 5 else 2000) for m in months}

    payload = {
        "household": {
            "people": {
                "parent_1": {"age": {"2026": 35}},
                "parent_2": {"age": {"2026": 35}},
                "child_1":  {"age": {"2026": 7}},
                "child_2":  {"age": {"2026": 4}},
            },
            "families": {
                "family_1": {
                    "members": ["parent_1", "parent_2", "child_1", "child_2"]
                }
            },
            "tax_units": {
                "tax_unit_1": {
                    "members": ["parent_1", "parent_2", "child_1", "child_2"]
                }
            },
            "households": {
                "household_1": {
                    "members": ["parent_1", "parent_2", "child_1", "child_2"],
                    "state_name": {"2026": "CA"},
                }
            },
            "spm_units": {
                "spm_unit_1": {
                    "members": ["parent_1", "parent_2", "child_1", "child_2"],
                    "snap_earned_income": earnings,
                    "snap": {m: None for m in months},
                }
            },
        }
    }

    response = requests.post(
        "https://household.api.policyengine.org/us/calculate",
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    snap = response.json()["result"]["spm_units"]["spm_unit_1"]["snap"]

    cliff = next((m for m in months if snap[m] == 0), None)
    print(f"SNAP cuts off at: {cliff}")
    ```

## The response

The response echoes your input keys exactly. The relevant slot is `result.spm_units.spm_unit_1.snap`:

```json
{
  "result": {
    "spm_units": {
      "spm_unit_1": {
        "snap": {
          "2026-01": 276.10,
          "2026-02": 276.10,
          "2026-03": 276.10,
          "2026-04": 276.10,
          "2026-05": 276.10,
          "2026-06": 0.00,
          "2026-07": 0.00,
          "2026-08": 0.00,
          "2026-09": 0.00,
          "2026-10": 0.00,
          "2026-11": 0.00,
          "2026-12": 0.00
        }
      }
    }
  }
}
```

These figures come from policyengine-us version 1.634.8 with 2026 SNAP parameters. Run the request against the live API for current numbers.

## How to read this

The cliff is the first month where SNAP drops to `0`. In this response, that's `2026-06` — the first month under the higher-paying job.

| Month       | Earnings | SNAP    |
| ----------- | -------- | ------- |
| 2026-01     | $1,500   | $276.10 |
| 2026-02     | $1,500   | $276.10 |
| 2026-03     | $1,500   | $276.10 |
| 2026-04     | $1,500   | $276.10 |
| 2026-05     | $1,500   | $276.10 |
| **2026-06** | **$2,000** | **$0.00** ⬅ cliff |
| 2026-07     | $2,000   | $0.00   |
| ...         | ...      | ...     |

The household stays at $0 for the rest of the year because the higher earnings exceed California's CalFresh eligibility threshold (200% of the federal poverty guideline for the household size, applied via broad-based categorical eligibility).

## Why this works

`snap_earned_income` and `snap` are both **MONTH-defined** variables in policyengine-us — each month is computed independently. Sending twelve different month-keyed inputs gives the engine twelve distinct months to evaluate, and requesting twelve month-keyed outputs returns each one as a separate result.

If you sent a year-keyed input instead — `{"2026": 21500}` — the API would split it evenly across all twelve months as $1,791.67 per month, and you would not see the cliff. The mid-year change has to be expressed as month-keyed inputs.

For the rules on how the API splits and broadcasts values across periods, see [Period keys](../period-keys.md).

## Variations

**Find the income at which the cliff fires.**
Hold the months fixed and vary earnings in finer steps — for example, scan from $1,500 to $2,000 in $50 increments by sending each value to a different month. The first response month with `0` corresponds to the breakpoint.

**Track multiple programs at once.**
Add `medicaid`, `tanf`, or `ctc` to the same `spm_unit_1` block as `null` per month. Each program comes back month by month so you can find the cliff for each one in the same request.

**Compare to a year of stable earnings.**
Send a second request with `"snap_earned_income": {"2026": 21500}` (the same annual total) and `"snap": {"2026": null}`. Compare the annual SNAP figures from the two requests to see how much the mid-year change costs the household over the year.

## Common mistakes

- **Mixing month inputs with annual outputs.** If you send month-keyed `snap_earned_income` but request `"snap": {"2026": null}`, the response includes a `warnings` array explaining that the unset months will read the engine's fallback value. Either send all twelve months as inputs *and* outputs, or send a yearly key for both.
- **Assuming a $0 means ineligible everywhere.** SNAP eligibility uses the gross income test, the net income test, and the resource test, with state-specific thresholds (BBCE in California raises the gross income limit to 200% FPG). A $0 in one month means the household failed at least one of those tests for *that month*, not necessarily for the whole year.
