install:
	pip install -U -e .[dev]

debug:
	FLASK_APP=policyengine_household_api.api FLASK_DEBUG=1 flask run --without-threads

test:
	pytest -vv --timeout=150 -rP tests/to_refactor tests/unit

test-with-auth:
	CONFIG_FILE=config/test_with_auth.yaml pytest -vv --timeout=150 -rP tests/integration_with_auth

debug-test:
	FLASK_DEBUG=1 pytest -vv --durations=0 --timeout=150 -rP tests

format:
	black . -l 79

# Docker Compose commands
docker-build:
	docker compose build

docker-up:
	docker compose up

docker-up-detached:
	docker compose up -d

docker-down:
	docker compose down

docker-dev:
	docker compose --profile dev up api-dev

docker-test:
	docker compose --profile test run --rm test

docker-test-auth:
	docker compose --profile test-auth run --rm test-with-auth

docker-logs:
	docker compose logs -f

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