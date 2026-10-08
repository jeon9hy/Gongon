"""중기육상예보 수집 기록(S08-3-2, D-042)

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mid_forecast_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("region_id", sa.String(8), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("raw_item", postgresql.JSONB(), nullable=True),
        sa.Column(
            "requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "uq_mid_forecast_runs_success",
        "mid_forecast_runs",
        ["issued_at", "region_id"],
        unique=True,
        postgresql_where=sa.text("status = 'success'"),
    )


def downgrade() -> None:
    op.drop_index("uq_mid_forecast_runs_success", table_name="mid_forecast_runs")
    op.drop_table("mid_forecast_runs")
