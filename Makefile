install:
	pip install -U -e ".[dev]" --config-settings editable_mode=compat

debug:
	FLASK_APP=policyengine_household_api.api FLASK_DEBUG=1 flask run --without-threads

test:
	pytest -vv --timeout=150 -rP tests

debug-test:
	FLASK_DEBUG=1 pytest -vv --durations=0 --timeout=150 -rP tests

format:
	black . -l 79

deploy:
	python gcp/export.py
	gcloud config set app/cloud_build_timeout 1800
	cp gcp/policyengine_household_api/* .
	y | gcloud app deploy --service-account=github-deployment@policyengine-household-api.iam.gserviceaccount.com
	rm app.yaml
	rm Dockerfile
	rm .gac.json

changelog:
	build-changelog changelog.yaml --output changelog.yaml --update-last-date --start-from 0.1.0 --append-file changelog_entry.yaml
	build-changelog changelog.yaml --org PolicyEngine --repo policyengine-household-api --output CHANGELOG.md --template .github/changelog_template.md
	bump-version changelog.yaml setup.py policyengine_household_api/constants.py
	rm changelog_entry.yaml || true
	touch changelog_entry.yaml 