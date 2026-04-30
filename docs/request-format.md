# Request format

The `/calculate` endpoint takes a JSON body with a `household` field. The household describes who lives there, what they earn, where they live, and which calculations to run.

## The shape

```json
{
  "household": {
    "people":     { "...": "..." },
    "families":   { "...": "..." },
    "tax_units":  { "...": "..." },
    "households": { "...": "..." },
    "spm_units":  { "...": "..." }
  }
}
```

Five entity groups, each a dict from entity-instance ID to the data for that instance. The IDs are partner-chosen strings — `"parent_1"`, `"household_1"`, `"my_client"` — they only need to be unique within their group.

## Entities

Each entity group represents a different administrative unit. The same person belongs to multiple entities at once.

| Entity       | What it is                                            | Variables that live here                |
| ------------ | ----------------------------------------------------- | --------------------------------------- |
| `people`     | Individuals                                           | `age`, `employment_income`, `is_disabled` |
| `families`   | Federal income tax filing family                      | `family_size`                           |
| `tax_units`  | The unit that files a tax return (often = family)     | `eitc`, `ctc`, `income_tax`             |
| `households` | The residential household for state-level benefits    | `state_name`, state EITC variants       |
| `spm_units`  | Supplemental Poverty Measure unit                     | `snap`, `wic`, `school_meal_subsidy`    |

Every person must be a member of every entity group. Even if you only want SNAP, you still need to include `tax_units`, `families`, and `households`.

## Members

Inside each entity instance, list the people that belong to it under `members`:

```json
"families": {
  "family_1": {
    "members": ["parent_1", "parent_2", "child_1", "child_2"]
  }
}
```

The strings in `members` must match person IDs from the `people` entity exactly.

## Inputs and outputs

Each variable lives under its entity, keyed by a period. There are two value types:

**Input** — a numeric, boolean, string, or enum value:

```json
"parent_1": {
  "employment_income": {"2026": 30000}
}
```

**Output request** — `null`, meaning "compute this and send it back":

```json
"spm_unit_1": {
  "snap": {"2026": null}
}
```

`null` is how you tell the API which variables to return. A request with no `null` slots returns nothing — the engine has nothing to compute.

## A complete request

A family of four in California, requesting SNAP, EITC, and CTC for 2026:

```json
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
        "members": ["parent_1", "parent_2", "child_1", "child_2"],
        "eitc": {"2026": null},
        "ctc":  {"2026": null}
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
```

For this household, the response returns:

| Variable | Value     |
| -------- | --------- |
| `eitc`   | $7,316.00 |
| `ctc`    | $4,400.00 |
| `snap`   | $3,924.54 |

## Where to find variable names

The full list of available variables for each country lives at `https://policyengine.org/{country_id}/variables`. Each variable has:

- A name (`snap`, `eitc`, `ctc`)
- An entity (`spm_units`, `tax_units`)
- A period definition (year or month — see [Period keys](period-keys.md))
- A value type (numeric, boolean, string, or enum)

You can also fetch metadata at runtime by calling `GET /{country_id}` against the API itself.

## What's next

- [Period keys](period-keys.md) — when to use `"2026"` vs `"2026-01"`
- [Response format](response-format.md) — how the API echoes your keys back
