import json
import os
from dataclasses import dataclass
from typing import Any
from urllib import error, request

import pytest


BASE_URL_ENV_VAR = "HOUSEHOLD_API_BASE_URL"
AUTH_TOKEN_ENV_VAR = "HOUSEHOLD_API_AUTH_TOKEN"
REQUEST_VERSION_ENV_VAR = "HOUSEHOLD_API_REQUEST_VERSION"
EXPECTED_CHANNEL_ENV_VAR = "HOUSEHOLD_API_EXPECTED_CHANNEL"
ROUTE_MODE_ENV_VAR = "HOUSEHOLD_API_ROUTE_MODE"
DEFAULT_TIMEOUT_SECONDS = 90


@dataclass
class DeployedResponse:
    status_code: int
    headers: dict[str, str]
    text: str

    def json(self) -> Any:
        return json.loads(self.text)


class DeployedApiClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def get(self, path: str, headers: dict[str, str] | None = None):
        return self._request("GET", path, headers=headers)

    def post(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
    ):
        return self._request(
            "POST",
            path,
            headers=headers,
            json_body=json_body,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> DeployedResponse:
        url = f"{self.base_url}/{path.lstrip('/')}"
        payload = None
        request_headers = headers.copy() if headers else {}

        if json_body is not None:
            payload = json.dumps(json_body).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")

        req = request.Request(
            url,
            data=payload,
            headers=request_headers,
            method=method,
        )

        try:
            with request.urlopen(
                req,
                timeout=DEFAULT_TIMEOUT_SECONDS,
            ) as response:
                return DeployedResponse(
                    status_code=response.status,
                    headers=dict(response.headers.items()),
                    text=response.read().decode("utf-8"),
                )
        except error.HTTPError as exc:
            return DeployedResponse(
                status_code=exc.code,
                headers=dict(exc.headers.items()),
                text=exc.read().decode("utf-8"),
            )


def _get_required_env_var(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        pytest.skip(f"{name} must be set to run deployed API tests")
    return value


@pytest.fixture(scope="session")
def base_url() -> str:
    return _get_required_env_var(BASE_URL_ENV_VAR)


@pytest.fixture(scope="session")
def auth_token() -> str:
    return _get_required_env_var(AUTH_TOKEN_ENV_VAR)


@pytest.fixture(scope="session")
def request_version() -> str | None:
    return os.getenv(REQUEST_VERSION_ENV_VAR, "").strip() or None


@pytest.fixture(scope="session")
def expected_channel() -> str | None:
    return os.getenv(EXPECTED_CHANNEL_ENV_VAR, "").strip() or None


@pytest.fixture(scope="session")
def route_mode() -> str | None:
    return os.getenv(ROUTE_MODE_ENV_VAR, "").strip() or None


@pytest.fixture(scope="session")
def deployed_api(base_url: str) -> DeployedApiClient:
    return DeployedApiClient(base_url)
