# Docker setup for PolicyEngine Household API

This repository publishes a hardened Docker image to GitHub Container Registry.

## Features

### Security hardening
- Multi-stage build to minimize image size
- Non-root user execution (uid 1000)
- Read-only root filesystem compatible
- No unnecessary capabilities
- Health checks included
- Regular vulnerability scanning with Trivy and Grype

### CI/CD pipeline
The GitHub Actions workflow:
- Builds on push to main and tags
- Multi-platform support (linux/amd64, linux/arm64)
- Automatic versioning from git tags
- SBOM (Software Bill of Materials) generation
- Vulnerability scanning and reporting
- Results uploaded to GitHub Security tab

## Using the image

Pull the latest image:
```bash
docker pull ghcr.io/policyengine/policyengine-household-api:latest
```

Run the container:
```bash
docker run -p 8080:8080 \
  -e AUTH0_ADDRESS_NO_DOMAIN=your_auth0_address \
  -e AUTH0_AUDIENCE_NO_DOMAIN=your_auth0_audience \
  ghcr.io/policyengine/policyengine-household-api:latest
```

## Building locally

```bash
docker build -t policyengine-household-api .
```

## Environment variables

Required environment variables:
- `AUTH0_ADDRESS_NO_DOMAIN`: Auth0 domain address
- `AUTH0_AUDIENCE_NO_DOMAIN`: Auth0 API audience
- `PORT`: Server port (defaults to 8080)

Optional for database connectivity:
- `USER_ANALYTICS_DB_USERNAME`
- `USER_ANALYTICS_DB_PASSWORD`
- `USER_ANALYTICS_DB_CONNECTION_NAME`
- `ANTHROPIC_API_KEY`

## Workflows

- **docker-publish.yml**: Builds and publishes images on push to main
- **security-scan.yml**: Weekly vulnerability scans of the latest image