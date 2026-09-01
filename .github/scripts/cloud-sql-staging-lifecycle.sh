#!/usr/bin/env bash
set -euo pipefail

readonly expected_project="policyengine-household-api"
readonly expected_instance="household-api-user-analytics-staging"

project="${CLOUD_SQL_PROJECT:-${expected_project}}"
instance="${CLOUD_SQL_INSTANCE:-${expected_instance}}"
gcloud_bin="${GCLOUD_BIN:-gcloud}"

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 start|stop" >&2
  exit 2
fi

action="$1"
case "${action}" in
  start)
    expected_policy="ALWAYS"
    ;;
  stop)
    expected_policy="NEVER"
    ;;
  *)
    echo "Unsupported action: ${action}. Expected start or stop." >&2
    exit 2
    ;;
esac

if [[ "${project}" != "${expected_project}" ]]; then
  echo "Refusing to modify unexpected Cloud SQL project: ${project}" >&2
  exit 2
fi

if [[ "${instance}" != "${expected_instance}" ]]; then
  echo "Refusing to modify unexpected Cloud SQL instance: ${instance}" >&2
  exit 2
fi

"${gcloud_bin}" sql instances patch "${instance}" \
  --project="${project}" \
  --activation-policy="${expected_policy}" \
  --quiet

description="$(
  "${gcloud_bin}" sql instances describe "${instance}" \
    --project="${project}" \
    --format="value(settings.activationPolicy,state)"
)"
read -r actual_policy actual_state <<< "${description}"

if [[ "${actual_policy}" != "${expected_policy}" ]]; then
  echo \
    "Cloud SQL activation policy is ${actual_policy:-unset}; expected ${expected_policy}." \
    >&2
  exit 1
fi

if [[ "${action}" == "start" && "${actual_state}" != "RUNNABLE" ]]; then
  echo \
    "Cloud SQL state is ${actual_state:-unset}; expected RUNNABLE after start." \
    >&2
  exit 1
fi

echo \
  "Cloud SQL staging instance ${action} verified: policy=${actual_policy}, state=${actual_state:-unset}."
