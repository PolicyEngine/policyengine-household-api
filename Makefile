.PHONY: help
help:  ## Print this message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-24s\033[0m %s\n", $$1, $$2}'

install: ## Install the full workspace with dev tooling
	uv sync --all-packages

debug: ## Run Flask app with FLASK_DEBUG=1
	FLASK_APP=policyengine_household_api.api FLASK_DEBUG=1 uv run flask run --without-threads --host=0.0.0.0

test: ## Run unit tests
	uv run pytest -vv --timeout=150 -rP .github/scripts tests/to_refactor tests/unit projects/analytics-api/tests

test-analytics-isolated: ## Run analytics writer tests in that member's own slim closure (what CI runs)
	uv sync --package policyengine-household-analytics-api
	uv run --no-sync pytest -vv --timeout=150 -rP projects/analytics-api/tests
	uv sync --all-packages

test-with-auth: ## Run integration tests
	CONFIG_FILE=config/test_with_auth.yaml uv run pytest -vv --timeout=150 -rP tests/integration_with_auth

debug-test: ## Run tests with FLASK_DEBUG=1
	FLASK_DEBUG=1 uv run pytest -vv --durations=0 --timeout=150 -rP tests

format: ## Format code with Ruff
	uv run ruff format .

format-check: ## Check code formatting with Ruff
	uv run ruff format --check .

deploy: ## Deploy to GCP
	python gcp/export.py
	gcloud config set app/cloud_build_timeout 1800
	cp gcp/policyengine_household_api/* .
	y | gcloud app deploy --service-account=github-deployment@policyengine-household-api.iam.gserviceaccount.com
	rm app.yaml
	rm Dockerfile
	rm .gac.json

changelog: ## Build changelog
	uv run python .github/scripts/update_versioning.py

COMPOSE_FILE ?= docker/docker-compose.yml
COMPOSE_EXTERNAL_FILE ?= docker/docker-compose.external.yml
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

.PHONY: docker-run-external
docker-run-external:  ## Run with external network (for multi-service setups)
	docker compose --file $(COMPOSE_FILE) --file $(COMPOSE_EXTERNAL_FILE) up

.PHONY: services-start
services-start:  ## Run the docker containers for supporting services (e.g. Redis)
	docker compose --file $(COMPOSE_FILE) up -d redis

.PHONY: services-start-external
services-start-external:  ## Start services with external network
	docker compose --file $(COMPOSE_FILE) --file $(COMPOSE_EXTERNAL_FILE) up -d redis

.PHONY: services-stop
services-stop:  ## Stop the docker containers for supporting services
	docker compose --file $(COMPOSE_FILE) down

.PHONY: docker-network-create
docker-network-create:  ## Create the external Docker network (for multi-service setups)
	docker network create $(DOCKER_NETWORK) || true

.PHONY: docker-console
docker-console:  ## Open a one-off container bash session
	@docker run -p 8080:5000 -v $(PWD):/code \
   --network $(DOCKER_NETWORK) \
   --rm --name $(DOCKER_CONSOLE) -it \
   $(DOCKER_IMG) bash
