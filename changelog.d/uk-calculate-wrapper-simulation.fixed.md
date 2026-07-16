UK `/calculate` requests no longer fail with a 500. policyengine-uk 2.43+
replaced its core `Simulation` subclass with a wrapper that builds its own
tax-benefit system and takes reforms through a `Scenario`;
`PolicyEngineCountry` now routes UK calculations through a dedicated
wrapper-style builder (applying reforms before construction so
structural-trigger parameters take effect) while other countries keep the
core path, and decodes the wrapper's string-array enum results.
