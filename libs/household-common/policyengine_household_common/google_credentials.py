"""Short-lived Google credentials for Modal household workers."""

from __future__ import annotations

from functools import cache
import os

from google.auth import identity_pool
from google.auth.credentials import Credentials


GOOGLE_WORKLOAD_IDENTITY_PROVIDER_ENV = (
    "HOUSEHOLD_GOOGLE_WORKLOAD_IDENTITY_PROVIDER"
)
GOOGLE_SERVICE_ACCOUNT_EMAIL_ENV = "HOUSEHOLD_GOOGLE_SERVICE_ACCOUNT_EMAIL"
MODAL_IDENTITY_TOKEN_ENV = "MODAL_IDENTITY_TOKEN"
GOOGLE_CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"


class _ModalSubjectTokenSupplier(identity_pool.SubjectTokenSupplier):
    """Read Modal's current OIDC token whenever Google refreshes access."""

    def get_subject_token(self, context, request) -> str:
        del context, request
        token = os.getenv(MODAL_IDENTITY_TOKEN_ENV)
        if not token:
            raise RuntimeError(
                f"{MODAL_IDENTITY_TOKEN_ENV} is required when household "
                "Google workload identity federation is configured"
            )
        return token


def _provider_audience(provider: str) -> str:
    provider = provider.removeprefix("//iam.googleapis.com/")
    if not provider.startswith("projects/"):
        raise RuntimeError(
            f"{GOOGLE_WORKLOAD_IDENTITY_PROVIDER_ENV} must be a Google "
            "Workload Identity provider resource name"
        )
    return f"//iam.googleapis.com/{provider}"


@cache
def get_household_google_credentials() -> Credentials | None:
    """Return Modal WIF credentials, or ``None`` to use normal ADC.

    Cloud Run and local commands do not receive the Modal-specific
    configuration and therefore retain Application Default Credentials.
    Modal workers receive both configuration values and exchange their
    injected identity token for an impersonated, short-lived credential.
    """

    provider = os.getenv(GOOGLE_WORKLOAD_IDENTITY_PROVIDER_ENV)
    service_account = os.getenv(GOOGLE_SERVICE_ACCOUNT_EMAIL_ENV)
    if not provider and not service_account:
        return None

    missing = [
        name
        for name, value in (
            (GOOGLE_WORKLOAD_IDENTITY_PROVIDER_ENV, provider),
            (GOOGLE_SERVICE_ACCOUNT_EMAIL_ENV, service_account),
            (MODAL_IDENTITY_TOKEN_ENV, os.getenv(MODAL_IDENTITY_TOKEN_ENV)),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            "Incomplete household Google workload identity configuration; "
            "missing: " + ", ".join(missing)
        )

    assert provider is not None
    assert service_account is not None
    return identity_pool.Credentials(
        audience=_provider_audience(provider),
        subject_token_type="urn:ietf:params:oauth:token-type:jwt",
        subject_token_supplier=_ModalSubjectTokenSupplier(),
        service_account_impersonation_url=(
            "https://iamcredentials.googleapis.com/v1/projects/-/"
            f"serviceAccounts/{service_account}:generateAccessToken"
        ),
        scopes=[GOOGLE_CLOUD_PLATFORM_SCOPE],
    )


def reset_household_google_credentials() -> None:
    """Discard credentials copied into a Modal memory snapshot."""

    get_household_google_credentials.cache_clear()
