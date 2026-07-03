FROM --platform=linux/amd64 python:3.13-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    "flask>=2.2" \
    "google-auth" \
    "google-cloud-storage" \
    "gunicorn" \
    "modal>=1.3.0" \
    "policyengine-observability[flask]>=1.0.0" \
    "pyyaml>=6"

COPY ./libs/household-api/policyengine_household_api /app/policyengine_household_api
COPY ./libs/household-common/policyengine_household_common /app/policyengine_household_common
COPY ./libs/household-api/pyproject.toml /app/pyproject.toml
COPY ./gcp/cloud_run/gateway_start.sh /app/start.sh
RUN chmod +x /app/start.sh

RUN groupadd policyapi && \
    useradd --gid policyapi --create-home policyapi && \
    chown -R policyapi:policyapi /app

ENV PYTHONUNBUFFERED=1
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD curl --fail --silent http://127.0.0.1:8080/liveness_check || exit 1

USER policyapi

CMD ["/app/start.sh"]
