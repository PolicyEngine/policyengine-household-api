UK `/calculate` requests no longer fail with a 500. policyengine-uk 2.43+
replaced its core `Simulation` subclass with a wrapper that builds its own
tax-benefit system and takes reforms as a constructor argument;
`PolicyEngineCountry.calculate` now detects which shape the country package
exposes and constructs the simulation accordingly, including decoding the
wrapper's string-array enum results.
