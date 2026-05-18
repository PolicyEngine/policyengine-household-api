#!/usr/bin/env bash
set -euo pipefail

modal_environment="${MODAL_ENVIRONMENT:-main}"
modal_get_url_script="${MODAL_GET_URL_SCRIPT:-.github/scripts/modal-get-url.sh}"
custom_domain_url="${HOUSEHOLD_MODAL_GATEWAY_CUSTOM_DOMAIN_URL:-https://household.api.policyengine.org}"

if [ "${modal_environment}" != "main" ]; then
  echo "Skipping custom-domain smoke check outside the main Modal environment."
  exit 0
fi

gateway_url="$(bash "${modal_get_url_script}")"
custom_domain_url="${custom_domain_url%/}"
gateway_url="${gateway_url%/}"

tmpdir="$(mktemp -d)"
trap 'rm -rf "${tmpdir}"' EXIT

gateway_versions="${tmpdir}/gateway-versions.json"
custom_versions="${tmpdir}/custom-domain-versions.json"

echo "Checking generated Modal gateway at ${gateway_url}"
curl -fsS "${gateway_url}/liveness_check" >/dev/null
curl -fsS "${gateway_url}/versions/us" > "${gateway_versions}"

echo "Checking production custom domain at ${custom_domain_url}"
curl -fsS "${custom_domain_url}/liveness_check" >/dev/null
curl -fsS "${custom_domain_url}/versions/us" > "${custom_versions}"

python - "${gateway_versions}" "${custom_versions}" <<'PY'
import json
import sys
from pathlib import Path


def load_versions(path: str, label: str) -> dict[str, str]:
    try:
        data = json.loads(Path(path).read_text())
    except json.JSONDecodeError as e:
        sys.exit(f"{label} /versions/us did not return JSON: {e}")

    if not isinstance(data, dict):
        sys.exit(f"{label} /versions/us returned a non-object JSON value")
    return data


gateway_versions = load_versions(sys.argv[1], "Generated Modal gateway")
custom_versions = load_versions(sys.argv[2], "Custom domain")

if gateway_versions != custom_versions:
    sys.exit(
        "Custom domain /versions/us does not match the generated Modal "
        f"gateway. generated={gateway_versions!r} custom={custom_versions!r}"
    )

print("Custom domain points at the deployed Modal gateway.")
PY
