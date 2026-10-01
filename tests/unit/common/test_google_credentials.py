from __future__ import annotations

import pytest

from policyengine_household_common.google_credentials import (
    GOOGLE_SERVICE_ACCOUNT_EMAIL_ENV,
    GOOGLE_WORKLOAD_IDENTITY_PROVIDER_ENV,
    MODAL_IDENTITY_TOKEN_ENV,
    get_household_google_credentials,
    reset_household_google_credentials,
)


PROVIDER = (
    "projects/120046258570/locations/global/"
    "workloadIdentityPools/modal-household-staging/providers/modal"
)
SERVICE_ACCOUNT = (
    "household-modal-staging@policyengine-household-api."
    "iam.gserviceaccount.com"
)


@pytest.fixture(autouse=True)
def reset_credentials_cache(monkeypatch):
    for name in (
        GOOGLE_WORKLOAD_IDENTITY_PROVIDER_ENV,
        GOOGLE_SERVICE_ACCOUNT_EMAIL_ENV,
        MODAL_IDENTITY_TOKEN_ENV,
    ):
        monkeypatch.delenv(name, raising=False)
    reset_household_google_credentials()
    yield
    reset_household_google_credentials()


def test_unconfigured_runtime_uses_application_default_credentials():
    assert get_household_google_credentials() is None


@pytest.mark.parametrize(
    ("name", "value"),
    [
        (GOOGLE_WORKLOAD_IDENTITY_PROVIDER_ENV, PROVIDER),
        (GOOGLE_SERVICE_ACCOUNT_EMAIL_ENV, SERVICE_ACCOUNT),
    ],
)
def test_partial_workload_identity_configuration_fails(
    name, value, monkeypatch
):
    monkeypatch.setenv(name, value)

    with pytest.raises(RuntimeError, match="Incomplete household Google"):
        get_household_google_credentials()


def test_workload_identity_credentials_use_provider_and_service_account(
    monkeypatch,
):
    monkeypatch.setenv(GOOGLE_WORKLOAD_IDENTITY_PROVIDER_ENV, PROVIDER)
    monkeypatch.setenv(GOOGLE_SERVICE_ACCOUNT_EMAIL_ENV, SERVICE_ACCOUNT)
    monkeypatch.setenv(MODAL_IDENTITY_TOKEN_ENV, "modal-token")

    credentials = get_household_google_credentials()

    assert credentials is not None
    assert credentials.info["audience"] == f"//iam.googleapis.com/{PROVIDER}"
    assert credentials.service_account_email == SERVICE_ACCOUNT
    assert credentials.retrieve_subject_token(None) == "modal-token"


def test_subject_token_supplier_reads_rotated_modal_token(monkeypatch):
    monkeypatch.setenv(GOOGLE_WORKLOAD_IDENTITY_PROVIDER_ENV, PROVIDER)
    monkeypatch.setenv(GOOGLE_SERVICE_ACCOUNT_EMAIL_ENV, SERVICE_ACCOUNT)
    monkeypatch.setenv(MODAL_IDENTITY_TOKEN_ENV, "first-token")
    credentials = get_household_google_credentials()

    monkeypatch.setenv(MODAL_IDENTITY_TOKEN_ENV, "rotated-token")

    assert credentials is not None
    assert credentials.retrieve_subject_token(None) == "rotated-token"


def test_reset_discards_cached_credentials(monkeypatch):
    monkeypatch.setenv(GOOGLE_WORKLOAD_IDENTITY_PROVIDER_ENV, PROVIDER)
    monkeypatch.setenv(GOOGLE_SERVICE_ACCOUNT_EMAIL_ENV, SERVICE_ACCOUNT)
    monkeypatch.setenv(MODAL_IDENTITY_TOKEN_ENV, "modal-token")
    first = get_household_google_credentials()

    reset_household_google_credentials()

    assert get_household_google_credentials() is not first


def test_provider_audience_accepts_fully_qualified_name(monkeypatch):
    monkeypatch.setenv(
        GOOGLE_WORKLOAD_IDENTITY_PROVIDER_ENV,
        f"//iam.googleapis.com/{PROVIDER}",
    )
    monkeypatch.setenv(GOOGLE_SERVICE_ACCOUNT_EMAIL_ENV, SERVICE_ACCOUNT)
    monkeypatch.setenv(MODAL_IDENTITY_TOKEN_ENV, "modal-token")

    credentials = get_household_google_credentials()

    assert credentials is not None
    assert credentials.info["audience"] == f"//iam.googleapis.com/{PROVIDER}"
