"""Baseline existing visits analytics table.

Revision ID: 20260508_0001
Revises:
Create Date: 2026-05-08 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260508_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "visits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_id", sa.String(length=255), nullable=False),
        sa.Column("datetime", sa.DateTime(), nullable=True),
        sa.Column("api_version", sa.String(length=32), nullable=True),
        sa.Column("endpoint", sa.String(length=64), nullable=True),
        sa.Column("method", sa.String(length=32), nullable=True),
        sa.Column("content_length_bytes", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("visits")
