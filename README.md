# PolicyEngine Household API

A version of the PolicyEngine API that runs the `calculate` endpoint over household object.

## Quick Start

### Local Development (without Docker)

```bash
make install
make debug
```

### Docker Compose

```bash
# Copy environment template
cp .env.example .env

# Start the API
make docker-up

# Or run in development mode with hot-reload
make docker-dev
```

### Running Tests

```bash
# Without Docker
make test

# With Docker Compose
make docker-test
```

## Docker Compose Services

| Command | Description |
|---------|-------------|
| `make docker-up` | Start the API service |
| `make docker-up-detached` | Start in background |
| `make docker-dev` | Start with hot-reload |
| `make docker-test` | Run unit tests |
| `make docker-test-auth` | Run auth integration tests |
| `make docker-down` | Stop all services |
| `make docker-logs` | View logs |

See `docker-compose.yml` for available services and profiles.

## Configuration

See [config/README.md](config/README.md) for detailed configuration options.

## Development Rules

1. Every endpoint should return a JSON object with at least a "status" and "message" field.

Please note that we do not support branched operations at this time.
