"""Add calculate variable usage analytics tables.

Revision ID: 20260508_0002
Revises: 20260508_0001
Create Date: 2026-05-08 00:00:01
"""

from alembic import op
import sqlalchemy as sa


revision = "20260508_0002"
down_revision = "20260508_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("visits") as batch_op:
        batch_op.alter_column(
            "client_id",
            existing_type=sa.String(length=255),
            nullable=True,
        )

    op.create_table(
        "calculate_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("visit_id", sa.Integer(), nullable=False),
        sa.Column("request_uuid", sa.String(length=36), nullable=False),
        sa.Column("client_id", sa.String(length=255), nullable=True),
        sa.Column("api_version", sa.String(length=32), nullable=True),
        sa.Column("country_id", sa.String(length=16), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=True),
        sa.Column("endpoint", sa.String(length=64), nullable=True),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("content_length_bytes", sa.Integer(), nullable=True),
        sa.Column("response_status_code", sa.Integer(), nullable=True),
        sa.Column(
            "distinct_variable_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "unsupported_variable_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "deprecated_allowlisted_variable_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["visit_id"],
            ["visits.id"],
            name="fk_calculate_requests_visit",
        ),
        sa.UniqueConstraint("request_uuid"),
    )
    op.create_index(
        "ix_calculate_requests_visit_id",
        "calculate_requests",
        ["visit_id"],
    )
    op.create_index(
        "ix_calculate_requests_client_created",
        "calculate_requests",
        ["client_id", "created_at"],
    )
    op.create_index(
        "ix_calculate_requests_country_created",
        "calculate_requests",
        ["country_id", "created_at"],
    )

    op.create_table(
        "calculate_request_variables",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("country_id", sa.String(length=16), nullable=False),
        sa.Column("api_version", sa.String(length=32), nullable=True),
        sa.Column("model_version", sa.String(length=64), nullable=True),
        sa.Column("response_status_code", sa.Integer(), nullable=True),
        sa.Column("variable_name", sa.String(length=255), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("period_granularity", sa.String(length=16), nullable=False),
        sa.Column(
            "entity_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "period_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "occurrence_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("availability_status", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["calculate_requests.id"],
            name="fk_calc_vars_request",
        ),
        sa.UniqueConstraint(
            "request_id",
            "variable_name",
            "entity_type",
            "source",
            name="ux_calc_vars_request_variable_entity_source",
        ),
    )
    op.create_index(
        "ix_calc_vars_variable_created",
        "calculate_request_variables",
        ["variable_name", "created_at"],
    )
    op.create_index(
        "ix_calc_vars_client_variable_created",
        "calculate_request_variables",
        ["client_id", "variable_name", "created_at"],
    )
    op.create_index(
        "ix_calc_vars_country_model_variable",
        "calculate_request_variables",
        ["country_id", "model_version", "variable_name"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_calc_vars_country_model_variable",
        table_name="calculate_request_variables",
    )
    op.drop_index(
        "ix_calc_vars_client_variable_created",
        table_name="calculate_request_variables",
    )
    op.drop_index(
        "ix_calc_vars_variable_created",
        table_name="calculate_request_variables",
    )
    op.drop_table("calculate_request_variables")

    op.drop_index(
        "ix_calculate_requests_country_created",
        table_name="calculate_requests",
    )
    op.drop_index(
        "ix_calculate_requests_client_created",
        table_name="calculate_requests",
    )
    op.drop_index(
        "ix_calculate_requests_visit_id",
        table_name="calculate_requests",
    )
    op.drop_table("calculate_requests")

    op.execute("UPDATE visits SET client_id = '' WHERE client_id IS NULL")
    with op.batch_alter_table("visits") as batch_op:
        batch_op.alter_column(
            "client_id",
            existing_type=sa.String(length=255),
            nullable=False,
        )
