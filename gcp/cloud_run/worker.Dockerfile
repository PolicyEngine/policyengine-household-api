FROM --platform=linux/amd64 python:3.13-slim AS builder

WORKDIR /build

RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -U uv

COPY ./pyproject.toml ./uv.lock /build/
COPY ./config /build/config
COPY ./libs /build/libs
COPY ./projects /build/projects

ENV UV_PROJECT_ENVIRONMENT=/opt/venv
RUN uv sync --frozen --no-dev \
    --package policyengine-household-failover-api --extra worker

ARG HOUSEHOLD_FAILOVER_PACKAGE_VERSIONS_JSON={}
ENV HOUSEHOLD_MODAL_PACKAGE_VERSIONS_JSON=${HOUSEHOLD_FAILOVER_PACKAGE_VERSIONS_JSON}

RUN /opt/venv/bin/python - <<'PY' > /tmp/country-package-specs.txt
from policyengine_household_api.deployment import (
    country_package_install_specs,
)

for spec in country_package_install_specs():
    print(spec)
PY
RUN if [ -s /tmp/country-package-specs.txt ]; then \
      xargs uv pip install --python /opt/venv/bin/python \
        < /tmp/country-package-specs.txt; \
    fi

RUN /opt/venv/bin/python -c \
    "from policyengine_household_api.deployment import preload_country_packages; preload_country_packages()"

FROM --platform=linux/amd64 python:3.13-slim AS production

WORKDIR /app

# Install ca-certificates explicitly so every build takes Debian's current CA
# store even when the base image is older, and point gRPC clients (such as
# Google Cloud Logging) at that store instead of the CA list bundled in
# grpcio, which still trusts the compromised eMudhra root "emSign ECC Root CA
# - G3" (https://emudhra.we-have-a-problem.com).
RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*
ENV GRPC_DEFAULT_SSL_ROOTS_FILE_PATH=/etc/ssl/certs/ca-certificates.crt

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /build/libs/household-api/pyproject.toml /app/pyproject.toml
COPY --from=builder /build/config /app/config
COPY --from=builder /build/libs/household-api/policyengine_household_api /app/policyengine_household_api
COPY --from=builder /build/libs/household-common/policyengine_household_common /app/policyengine_household_common
COPY --from=builder /build/libs/household-analytics/policyengine_household_analytics /app/policyengine_household_analytics
COPY --from=builder /build/projects/cloud-run-failover-api/policyengine_household_failover /app/policyengine_household_failover
COPY ./gcp/cloud_run/worker_start.sh /app/start.sh
RUN chmod +x /app/start.sh

RUN groupadd policyapi && \
    useradd --gid policyapi --create-home policyapi && \
    chown -R policyapi:policyapi /app

ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
  CMD curl --fail --silent http://127.0.0.1:8080/liveness_check || exit 1

USER policyapi

CMD ["/app/start.sh"]
