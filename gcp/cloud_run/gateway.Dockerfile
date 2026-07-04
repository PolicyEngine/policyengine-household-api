FROM --platform=linux/amd64 python:3.13-slim AS builder

WORKDIR /build

RUN pip install --no-cache-dir -U uv

# The workspace root manifest plus every member manifest: uv needs all member
# pyprojects present to parse the workspace, even when none are installed.
COPY ./pyproject.toml ./uv.lock /build/
COPY ./libs/household-api/pyproject.toml ./libs/household-api/README.md /build/libs/household-api/
COPY ./libs/household-common/pyproject.toml ./libs/household-common/README.md /build/libs/household-common/
COPY ./libs/household-analytics/pyproject.toml ./libs/household-analytics/README.md /build/libs/household-analytics/
COPY ./projects/analytics-api/pyproject.toml ./projects/analytics-api/README.md /build/projects/analytics-api/
COPY ./projects/cloud-run-failover-api/pyproject.toml ./projects/cloud-run-failover-api/README.md /build/projects/cloud-run-failover-api/
COPY ./projects/modal-api/pyproject.toml ./projects/modal-api/README.md /build/projects/modal-api/

ENV UV_PROJECT_ENVIRONMENT=/opt/venv
# Base closure only (no worker extra): the gateway image stays free of
# country model packages, and its dependencies are lockfile-pinned.
RUN uv sync --frozen --no-install-workspace --no-dev \
    --package policyengine-household-failover-api

FROM --platform=linux/amd64 python:3.13-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
COPY ./projects/cloud-run-failover-api/policyengine_household_failover /app/policyengine_household_failover
COPY ./libs/household-common/policyengine_household_common /app/policyengine_household_common
COPY ./gcp/cloud_run/gateway_start.sh /app/start.sh
RUN chmod +x /app/start.sh

RUN groupadd policyapi && \
    useradd --gid policyapi --create-home policyapi && \
    chown -R policyapi:policyapi /app

ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD curl --fail --silent http://127.0.0.1:8080/liveness_check || exit 1

USER policyapi

CMD ["/app/start.sh"]
