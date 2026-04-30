# What's my client's SNAP for 2026?

Compute a household's annual SNAP allotment in a single API call. This is the simplest useful request — one household, one variable, one period.

## What you'll learn

- The minimal household payload needed to run a calculation
- How to send an annual income and request an annual benefit
- Where the result lives in the response

## The household

A family of four in California: two parents, two children. The earning parent makes $30,000 per year.

## The request

=== "curl"

    ```bash
    curl https://household.api.policyengine.org/us/calculate \
      -H "Content-Type: application/json" \
      -d @- <<'JSON'
    {
      "household": {
        "people": {
          "parent_1": {
            "age": {"2026": 35},
            "employment_income": {"2026": 30000}
          },
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
            "snap": {"2026": null}
          }
        }
      }
    }
    JSON
    ```

=== "Python"

    ```python
    import requests

    payload = {
        "household": {
            "people": {
                "parent_1": {
                    "age": {"2026": 35},
                    "employment_income": {"2026": 30000},
                },
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
                    "snap": {"2026": None},
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
    snap = response.json()["result"]["spm_units"]["spm_unit_1"]["snap"]["2026"]
    print(f"Annual SNAP: ${snap:,.2f}")
    ```

## The response

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

These figures come from policyengine-us 1.634.8 with 2026 SNAP parameters. SNAP updates each October (federal fiscal year), so monthly amounts vary slightly across the year — the annual figure is the sum of all twelve months.

## Why every entity is required

The household payload includes five entity groups: `people`, `families`, `tax_units`, `households`, and `spm_units`. Each represents a different administrative unit:

| Entity      | Purpose                                            | Example use         |
| ----------- | -------------------------------------------------- | ------------------- |
| `people`    | Individuals and their personal attributes          | Age, earnings       |
| `families`  | Federal income tax filing family unit              | Child Tax Credit    |
| `tax_units` | Tax filers (often equal to family)                 | Income tax          |
| `households`| Residential household for state benefits           | State EITC, SNAP    |
| `spm_units` | Supplemental Poverty Measure unit                  | SNAP, school meals  |

Every person needs to be a member of every entity group, even if you only care about one program. Omitting a group raises a 400.

## Variations

**Request multiple programs at once.**
Add other variables alongside `snap`. The request returns all of them in one round trip:

```jsonc
"spm_units": {
  "spm_unit_1": {
    "members": ["parent_1", "parent_2", "child_1", "child_2"],
    "snap": {"2026": null},
    "wic": {"2026": null}
  }
},
"tax_units": {
  "tax_unit_1": {
    "members": ["parent_1", "parent_2", "child_1", "child_2"],
    "eitc": {"2026": null},
    "ctc": {"2026": null}
  }
}
```

**Try a different state.**
Change `state_name` to any two-letter state code. SNAP allotments differ between states because of broad-based categorical eligibility (BBCE) thresholds and standard utility allowances.

**See month-by-month detail.**
Replace `"snap": {"2026": null}` with twelve month keys to get a per-month breakdown. See [When does my client lose SNAP this year?](eligibility-cliff.md) for the pattern.

## What's next

- [Request format](../request-format.md) — the entity structure in detail
- [Period keys](../period-keys.md) — when to use year keys vs month keys
- [When does my client lose SNAP this year?](eligibility-cliff.md) — the month-keyed equivalent of this recipe
