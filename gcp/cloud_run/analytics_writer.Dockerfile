FROM --platform=linux/amd64 python:3.13-slim AS builder

WORKDIR /build

RUN pip install --no-cache-dir -U uv

# The workspace root manifest plus every member manifest: uv needs all member
# pyprojects present to parse the workspace, even when none are installed.
COPY ./pyproject.toml ./uv.lock /build/
COPY ./libs/household-api/pyproject.toml ./libs/household-api/README.md /build/libs/household-api/
COPY ./libs/household-common/pyproject.toml ./libs/household-common/README.md /build/libs/household-common/
COPY ./libs/household-analytics/pyproject.toml ./libs/household-analytics/README.md /build/libs/household-analytics/

ENV UV_PROJECT_ENVIRONMENT=/opt/venv
RUN uv sync --frozen --no-install-workspace --only-group analytics-writer

FROM --platform=linux/amd64 python:3.13-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
COPY ./libs/household-api/policyengine_household_api /app/policyengine_household_api
COPY ./libs/household-common/policyengine_household_common /app/policyengine_household_common
COPY ./libs/household-analytics/policyengine_household_analytics /app/policyengine_household_analytics
COPY ./config /app/config
COPY ./libs/household-api/pyproject.toml /app/pyproject.toml
COPY ./gcp/cloud_run/analytics_writer_start.sh /app/start.sh
RUN chmod +x /app/start.sh

RUN groupadd policyapi && \
    useradd --gid policyapi --create-home policyapi && \
    chown -R policyapi:policyapi /app

ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD curl --fail --silent http://127.0.0.1:8080/liveness_check || exit 1

USER policyapi

CMD ["/app/start.sh"]
