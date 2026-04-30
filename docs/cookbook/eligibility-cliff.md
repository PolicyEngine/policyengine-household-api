# When does my client lose SNAP this year?

Find the month in which SNAP eligibility ends after a mid-year income change — in a single API call, with no extra round trips.

This recipe uses month-keyed inputs for a variable that changes month over month (`snap_earned_income`) and month-keyed outputs for the variable you want to track (`snap`). The response gives back twelve monthly SNAP figures, and the first month with `0` is the cliff.

## What you'll learn

- How to send a different value for each month of the same variable
- How to request twelve monthly outputs in one request
- How to read the response to find a benefit cliff

## The household

A family of four in California: two adults and two children. One adult earns $2,500 per month from January through May, then takes a higher-paying job and earns $4,500 per month from June through December.

| Period            | Gross earnings | Annual to date |
| ----------------- | -------------- | -------------- |
| Jan–May (5 mo)    | $2,500/mo      | $12,500        |
| Jun–Dec (7 mo)    | $4,500/mo      | $44,000        |
| Full year         | —              | $44,000        |

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
              "2026-01": 2500, "2026-02": 2500, "2026-03": 2500,
              "2026-04": 2500, "2026-05": 2500,
              "2026-06": 4500, "2026-07": 4500, "2026-08": 4500,
              "2026-09": 4500, "2026-10": 4500, "2026-11": 4500,
              "2026-12": 4500
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
    earnings = {m: (2500 if int(m[-2:]) <= 5 else 4500) for m in months}

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
          "2026-01": 715.50,
          "2026-02": 715.50,
          "2026-03": 715.50,
          "2026-04": 715.50,
          "2026-05": 715.50,
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

!!! note "Numbers are illustrative"
    The exact dollar values depend on the policyengine-us model version and the SNAP parameters in effect for that period. Run the request against the live API for the current numbers.

## How to read this

The cliff is the first month where SNAP drops to `0`. In this response, that's `2026-06` — the first month under the higher-paying job.

| Month   | Earnings | SNAP    |
| ------- | -------- | ------- |
| 2026-01 | $2,500   | $715.50 |
| 2026-02 | $2,500   | $715.50 |
| 2026-03 | $2,500   | $715.50 |
| 2026-04 | $2,500   | $715.50 |
| 2026-05 | $2,500   | $715.50 |
| **2026-06** | **$4,500** | **$0.00** ⬅ cliff |
| 2026-07 | $4,500   | $0.00   |
| ...     | ...      | ...     |

## Why this works

`snap_earned_income` and `snap` are both **MONTH-defined** variables in policyengine-us — each month is computed independently. Sending twelve different month-keyed inputs gives the engine twelve distinct months to evaluate, and requesting twelve month-keyed outputs returns each one as a separate result.

If you sent a year-keyed input instead — `{"2026": 44000}` — the API would split it evenly across all twelve months as $3,666.67 per month, and you would not see the cliff. The mid-year change has to be expressed as month-keyed inputs.

For the rules on how the API splits and broadcasts values across periods, see [Period keys](../period-keys.md).

## Variations

**Find the income at which the cliff fires.**
Hold the months fixed and vary earnings in finer steps — for example, scan from $3,500 to $5,000 in $100 increments by sending each value to a different month. The response month with the first `0` corresponds to the breakpoint.

**Track multiple programs at once.**
Add `medicaid`, `tanf`, or `ctc` to the same `spm_unit_1` block as `null` per month. Each program comes back month by month so you can find the cliff for each one in the same request.

**Compare to a year of stable earnings.**
Send a second request with `"snap_earned_income": {"2026": 44000}` (the same annual total) and `"snap": {"2026": null}`. Compare the annual SNAP figures from the two requests to see how much the mid-year change costs the household over the year.

## Common mistakes

- **Mixing month inputs with annual outputs.** If you send month-keyed `snap_earned_income` but request `"snap": {"2026": null}`, the response includes a `warnings` array explaining that the unset months will read the engine's fallback value. Either send all twelve months as inputs *and* outputs, or send a yearly key for both.
- **Assuming a $0 means ineligible everywhere.** SNAP eligibility uses the gross income test, the net income test, and the resource test. A $0 in one month means the household failed at least one of those tests for *that month*, not necessarily for the whole year.
