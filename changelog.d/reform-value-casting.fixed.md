Reform values in `/calculate` policy dicts are now cast explicitly to the
parameter's type. Boolean parameters: string `"false"` previously applied
as `True` (a Python truthiness accident) and now applies as `False`;
accepted forms are true/false, `"true"`/`"false"`, `"1"`/`"0"`, and
numbers, while ambiguous strings (e.g. `"2"`, `"1.0"`) and `null` — which
previously coerced silently — now return a descriptive error. The
parameter's type is now read from its most recent non-null value instead
of its oldest, so parameters introduced with null placeholders no longer
crash valid reforms.
