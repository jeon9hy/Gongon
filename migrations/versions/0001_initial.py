"""현장·예보 수집·판정 테이블

Revision ID: 0001
Revises:
Create Date: 2026-10-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("address", sa.String(200), nullable=False),
        sa.Column("latitude_deg", sa.Float(), nullable=False),
        sa.Column("longitude_deg", sa.Float(), nullable=False),
        sa.Column("grid_nx", sa.Integer(), nullable=False),
        sa.Column("grid_ny", sa.Integer(), nullable=False),
        sa.Column("work_start_local", sa.Time(), nullable=False),
        sa.Column("work_end_local", sa.Time(), nullable=False),
        sa.Column("work_types", postgresql.ARRAY(sa.String(40)), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "forecast_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("base_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("grid_nx", sa.Integer(), nullable=False),
        sa.Column("grid_ny", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("raw_items", postgresql.JSONB(), nullable=True),
        sa.Column(
            "requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "uq_forecast_runs_success",
        "forecast_runs",
        ["base_at", "grid_nx", "grid_ny"],
        unique=True,
        postgresql_where=sa.text("status = 'success'"),
    )
    op.create_table(
        "judgments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id"), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("work_type", sa.String(40), nullable=False),
        sa.Column("work_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("work_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verdict", sa.String(10), nullable=False),
        sa.Column("rule_version", sa.String(40), nullable=False),
        sa.Column("rule_source", sa.String(200), nullable=False),
        sa.Column("rule_source_verified", sa.Boolean(), nullable=False),
        sa.Column("grid_nx", sa.Integer(), nullable=False),
        sa.Column("grid_ny", sa.Integer(), nullable=False),
        sa.Column(
            "forecast_run_id", sa.Integer(), sa.ForeignKey("forecast_runs.id"), nullable=True
        ),
        sa.Column("forecast_issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("hours", postgresql.JSONB(), nullable=False),
        sa.Column("windows", postgresql.JSONB(), nullable=False),
        sa.Column(
            "judged_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_judgments_site_target", "judgments", ["site_id", "target_date"])
    op.create_index(
        "uq_judgments_reuse_key",
        "judgments",
        [
            "site_id",
            "target_date",
            "work_type",
            "forecast_issued_at",
            "rule_version",
            "grid_nx",
            "grid_ny",
            "work_start_at",
            "work_end_at",
        ],
        unique=True,
        postgresql_where=sa.text("forecast_issued_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_table("judgments")
    op.drop_table("forecast_runs")
    op.drop_table("sites")
