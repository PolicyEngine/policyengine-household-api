.PHONY: help build test deploy clean local-build local-test local-run

# Default target
help:
	@echo "Available commands:"
	@echo "  build          - Build production Docker image"
	@echo "  test           - Run tests locally"
	@echo "  deploy         - Deploy to App Engine (requires gcloud auth)"
	@echo "  clean          - Clean up Docker images and containers"
	@echo "  local-build    - Build and run locally with docker-compose"
	@echo "  local-test     - Test the local container"
	@echo "  local-run      - Start local development environment"

# Build production Docker image
build:
	docker build -f Dockerfile.production -t policyengine-household-api:latest ..

# Run tests locally
test:
	python -m pytest ../tests/ -v --cov=policyengine_household_api

# Deploy to App Engine (requires gcloud authentication)
deploy:
	gcloud app deploy app.yaml --version=$(shell git rev-parse --short HEAD)

# Clean up Docker resources
clean:
	docker system prune -f
	docker image prune -f
	docker container prune -f

# Build and run locally with docker-compose
local-build:
	docker-compose build

# Test the local container
local-test:
	docker-compose up -d
	sleep 30
	curl -f http://localhost:8080/health || exit 1
	docker-compose down

# Start local development environment
local-run:
	docker-compose up

# Stop local development environment
local-stop:
	docker-compose down

# View logs
logs:
	docker-compose logs -f api

# Shell into running container
shell:
	docker-compose exec api bash

# Health check
health:
	curl -f http://localhost:8080/liveness_check

# Readiness check
readiness:
	curl -f http://localhost:8080/readiness-check
