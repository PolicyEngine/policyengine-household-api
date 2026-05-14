from policyengine_household_api.data.analytics_setup import db
from policyengine_household_api.models.analytics import (
    AnalyticsHttpMethod,
    AvailabilityStatus,
    PeriodGranularity,
    VariableSource,
)
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import mapped_column


def _enum_values(enum_type) -> tuple[str, ...]:
    return tuple(member.value for member in enum_type)


class Visit(db.Model):
    # Note that the model represents one visit,
    # while the table name is plural
    __tablename__ = "visits"
    id = mapped_column(Integer, primary_key=True)
    client_id = mapped_column(String(255), nullable=True)
    datetime = mapped_column(DateTime)
    api_version = mapped_column(String(32))
    endpoint = mapped_column(String(64))
    method = mapped_column(
        String(32),
        info={"options": _enum_values(AnalyticsHttpMethod)},
    )
    content_length_bytes = mapped_column(Integer)


class CalculateRequest(db.Model):
    """One analytics record for an inbound /calculate request."""

    __tablename__ = "calculate_requests"

    id = mapped_column(Integer, primary_key=True)
    visit_id = mapped_column(
        Integer,
        ForeignKey("visits.id"),
        nullable=False,
    )
    request_uuid = mapped_column(String(36), nullable=False, unique=True)
    client_id = mapped_column(String(255), nullable=True)
    api_version = mapped_column(String(32), nullable=True)
    country_id = mapped_column(String(16), nullable=False)
    model_version = mapped_column(String(64), nullable=True)
    endpoint = mapped_column(String(64), nullable=True)
    method = mapped_column(
        String(16),
        nullable=False,
        info={"options": _enum_values(AnalyticsHttpMethod)},
    )
    content_length_bytes = mapped_column(Integer, nullable=True)
    response_status_code = mapped_column(Integer, nullable=True)
    distinct_variable_count = mapped_column(Integer, nullable=False, default=0)
    unsupported_variable_count = mapped_column(
        Integer, nullable=False, default=0
    )
    deprecated_allowlisted_variable_count = mapped_column(
        Integer, nullable=False, default=0
    )
    created_at = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index(
            "ix_calculate_requests_client_created", "client_id", "created_at"
        ),
        Index("ix_calculate_requests_visit_id", "visit_id"),
        Index(
            "ix_calculate_requests_country_created",
            "country_id",
            "created_at",
        ),
    )


class CalculateRequestVariable(db.Model):
    """A grouped variable-usage row derived from one calculate request."""

    __tablename__ = "calculate_request_variables"

    id = mapped_column(Integer, primary_key=True)
    request_id = mapped_column(
        Integer,
        ForeignKey("calculate_requests.id"),
        nullable=False,
    )
    client_id = mapped_column(String(255), nullable=True)
    created_at = mapped_column(DateTime, nullable=False)
    country_id = mapped_column(String(16), nullable=False)
    api_version = mapped_column(String(32), nullable=True)
    model_version = mapped_column(String(64), nullable=True)
    response_status_code = mapped_column(Integer, nullable=True)
    variable_name = mapped_column(String(255), nullable=False)
    variable_name_truncated = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    entity_type = mapped_column(String(64), nullable=False)
    source = mapped_column(
        String(32),
        nullable=False,
        info={"options": _enum_values(VariableSource)},
    )
    period_granularity = mapped_column(
        String(16),
        nullable=False,
        info={"options": _enum_values(PeriodGranularity)},
    )
    entity_count = mapped_column(Integer, nullable=False, default=0)
    period_count = mapped_column(Integer, nullable=False, default=0)
    occurrence_count = mapped_column(Integer, nullable=False, default=0)
    availability_status = mapped_column(
        String(32),
        nullable=False,
        info={"options": _enum_values(AvailabilityStatus)},
    )

    # Do not make request_id + variable_name unique: overlong variable names
    # are intentionally capped before persistence, so different originals can
    # share one stored representation.
    __table_args__ = (
        Index("ix_calc_vars_request_id", "request_id"),
        Index(
            "ix_calc_vars_variable_created",
            "variable_name",
            "created_at",
        ),
        Index(
            "ix_calc_vars_client_variable_created",
            "client_id",
            "variable_name",
            "created_at",
        ),
        Index(
            "ix_calc_vars_country_model_variable",
            "country_id",
            "model_version",
            "variable_name",
        ),
    )


class TestCase(db.Model):
    """A saved household payload partners run against the API for migration
    validation. Owned by the partner client_id that created it; staff
    callers can read across all client_ids via the as_client_id query
    param (Phase 2)."""

    # Pytest auto-collects classes named ``Test*``; this is a SQLAlchemy
    # model, not a test class.
    __test__ = False

    __tablename__ = "test_cases"

    id = mapped_column(Integer, primary_key=True)
    client_id = mapped_column(String(255), nullable=False)
    name = mapped_column(String(255), nullable=False)
    description = mapped_column(Text, nullable=True)
    payload = mapped_column(JSON, nullable=False)
    created_at = mapped_column(DateTime, nullable=False)
    updated_at = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index("ix_test_cases_client_id", "client_id"),
        Index("ix_test_cases_client_updated", "client_id", "updated_at"),
    )


class TestCaseAudit(db.Model):
    """Append-only log of test-case mutations. Powers the staff activity
    feed and provides forensic history independent of the test_cases
    row's current state (deletions still leave a trail)."""

    # Pytest auto-collects classes named ``Test*``; this is a SQLAlchemy
    # model, not a test class.
    __test__ = False

    __tablename__ = "test_case_audits"

    id = mapped_column(Integer, primary_key=True)
    # Not a ForeignKey so deletes don't cascade-wipe the audit history.
    test_case_id = mapped_column(Integer, nullable=False)
    # The owning partner client_id — used for activity-feed scoping.
    client_id = mapped_column(String(255), nullable=False)
    # The client_id that performed the action — equals client_id for
    # partner self-service, differs when staff edit on a partner's
    # behalf (Phase 2+).
    actor_client_id = mapped_column(String(255), nullable=False)
    action = mapped_column(
        String(16),
        nullable=False,
        info={"options": ("created", "updated", "deleted")},
    )
    name_snapshot = mapped_column(String(255), nullable=True)
    occurred_at = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index("ix_test_case_audits_client_occurred", "client_id", "occurred_at"),
        Index("ix_test_case_audits_test_case_id", "test_case_id"),
    )
