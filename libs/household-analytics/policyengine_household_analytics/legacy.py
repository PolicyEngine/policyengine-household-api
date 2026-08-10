"""Stable identities for analytics records recovered from legacy visits."""

from uuid import UUID, uuid5


# This namespace is UUIDv5(URL, PolicyEngine's canonical legacy-visits URL).
# It is persisted as a literal because changing it would change every derived
# request UUID and break retry-safe backfills.
LEGACY_VISIT_REQUEST_NAMESPACE = UUID("5b06406a-e2e2-5e53-a25f-9082a2aa7849")


def legacy_visit_request_uuid(visit_id: int) -> str:
    """Return the deterministic request UUID assigned to a legacy visit."""

    return str(uuid5(LEGACY_VISIT_REQUEST_NAMESPACE, str(visit_id)))
