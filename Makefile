.PHONY: help
help:  ## Print this message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-24s\033[0m %s\n", $$1, $$2}'

install: ## Install Python dependencies
	pip install -U -e .[dev]

debug: ## Run Flask app with FLASK_DEBUG=1
	FLASK_APP=policyengine_household_api.api FLASK_DEBUG=1 flask run --without-threads

test: ## Run unit tests
	pytest -vv --timeout=150 -rP tests/to_refactor tests/unit

test-with-auth: ## Run integration tests
	CONFIG_FILE=config/test_with_auth.yaml pytest -vv --timeout=150 -rP tests/integration_with_auth

debug-test: ## Run tests with FLASK_DEBUG=1
	FLASK_DEBUG=1 pytest -vv --durations=0 --timeout=150 -rP tests

format: ## Run black
	black . -l 79

deploy: ## Deploy to GCP
	python gcp/export.py
	gcloud config set app/cloud_build_timeout 1800
	cp gcp/policyengine_household_api/* .
	y | gcloud app deploy --service-account=github-deployment@policyengine-household-api.iam.gserviceaccount.com
	rm app.yaml
	rm Dockerfile
	rm .gac.json

changelog: ## Build changelog
	build-changelog changelog.yaml --output changelog.yaml --update-last-date --start-from 0.1.0 --append-file changelog_entry.yaml
	build-changelog changelog.yaml --org PolicyEngine --repo policyengine-household-api --output CHANGELOG.md --template .github/changelog_template.md
	bump-version changelog.yaml setup.py policyengine_household_api/constants.py
	rm changelog_entry.yaml || true
	touch changelog_entry.yaml

COMPOSE_FILE ?= docker/docker-compose.yml
DOCKER_IMG ?= policyengine:policyengine-household-api
DOCKER_NAME ?= policyengine-household-api
ifeq (, $(shell which docker))
DOCKER_CONTAINER_ID := docker-is-not-installed
else
DOCKER_CONTAINER_ID := $(shell docker ps --filter ancestor=$(DOCKER_IMG) --format "{{.ID}}")
endif
DOCKER_NETWORK ?= policyengine-api_default
DOCKER_CONSOLE ?= policyengine-api-console

.PHONY: docker-build
docker-build: ## Build the docker image
	docker compose --file $(COMPOSE_FILE) build --force-rm

.PHONY: docker-run
docker-run:  ## Run the app as docker container with supporting services
	docker compose --file $(COMPOSE_FILE) up

.PHONY: services-start
services-start:  ## Run the docker containers for supporting services (e.g. Redis)
	docker compose --file $(COMPOSE_FILE) up -d redis

.PHONY: docker-console
docker-console:  ## Open a one-off container bash session
	@docker run -p 8080:5000 -v $(PWD):/code \
   --network $(DOCKER_NETWORK) \
   --rm --name $(DOCKER_CONSOLE) -it \
   $(DOCKER_IMG) bash