"""판정 실행 기록(D-044): 같은 예보로 다시 판정해도 마지막 확인 시각을 보여 준다

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "judgment_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id"), nullable=False),
        sa.Column("ran_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("forecast_issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", sa.String(20), nullable=False),
        sa.Column("stored_count", sa.Integer(), nullable=False),
    )
    op.create_index("ix_judgment_runs_site_ran", "judgment_runs", ["site_id", "ran_at"])


def downgrade() -> None:
    op.drop_index("ix_judgment_runs_site_ran", table_name="judgment_runs")
    op.drop_table("judgment_runs")
