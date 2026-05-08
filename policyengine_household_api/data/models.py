from policyengine_household_api.data.analytics_setup import db
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import mapped_column


class Visit(db.Model):
    # Note that the model represents one visit,
    # while the table name is plural
    __tablename__ = "visits"
    id = mapped_column(Integer, primary_key=True)
    client_id = mapped_column(String(255), nullable=True)
    datetime = mapped_column(DateTime)
    api_version = mapped_column(String(32))
    endpoint = mapped_column(String(64))
    method = mapped_column(String(32))
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
    method = mapped_column(String(16), nullable=False)
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
    entity_type = mapped_column(String(64), nullable=False)
    source = mapped_column(String(32), nullable=False)
    period_granularity = mapped_column(String(16), nullable=False)
    entity_count = mapped_column(Integer, nullable=False, default=0)
    period_count = mapped_column(Integer, nullable=False, default=0)
    occurrence_count = mapped_column(Integer, nullable=False, default=0)
    availability_status = mapped_column(String(32), nullable=False)

    __table_args__ = (
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
        UniqueConstraint(
            "request_id",
            "variable_name",
            "entity_type",
            "source",
            name="ux_calc_vars_request_variable_entity_source",
        ),
    )
