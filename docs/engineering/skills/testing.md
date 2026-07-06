# Testing Skill

Use this skill whenever adding, moving, or reviewing tests.

## Canonical Layout

- Put unit tests under `tests/unit/`, except analytics writer tests,
  which live in `projects/analytics-api/tests/` so PR CI can run them in
  that member's slim dependency closure (see
  `docs/engineering/skills/monorepo-layout.md`).
- Put authenticated integration tests under `tests/integration_with_auth/`.
- Put deployed-service tests under `tests/deployed/`.
- Treat `tests/to_refactor/` as a legacy lane. Do not add new tests there
  unless the surrounding task is explicitly about migrating or preserving that
  lane.
- Keep shared test data under `tests/data/`.

## Fixtures And Helpers

- Keep reusable mocks, patches, and setup helpers in `tests/fixtures/` or the
  narrowest applicable `conftest.py`.
- Test files should focus on arranging inputs and asserting behavior, not on
  defining reusable patch machinery inline.
- Put domain-specific fixtures in the narrowest fixture module that covers the
  tests that use them.
- Do not import from `tests.conftest`; pytest discovers fixtures automatically.
- Avoid importing helpers across unrelated test lanes. If a helper is shared
  broadly, move it to `tests/fixtures/` or another explicit support module.

## Dependency Boundaries

- Unit tests should not require real network credentials, deployed services,
  Google Cloud, Auth0, or household API credentials. Mock those seams.
- Authenticated and deployed tests may require external configuration, but they
  should make those requirements explicit and skip or fail clearly when required
  credentials are unavailable.
- Prefer focused tests around the changed behavior. Broaden coverage when a
  change touches endpoint behavior, database persistence, analytics contracts,
  authentication, or shared request parsing.

## Verification

Run the narrowest relevant test slice while developing. Before handing off a PR
that changes test layout or shared behavior, run the relevant CI-facing targets
when practical:

```bash
make format-check
make test
make test-with-auth
```

If `make test-with-auth` cannot run because local Auth0 configuration is
unavailable, say that explicitly in the handoff and rely on PR CI for that lane.
