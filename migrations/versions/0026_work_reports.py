"""작업일보: 작업별 실제 결과 (C14-2, D-112)

작업 하나에 한 행. 결과(했음·일부·못함), 원인(변경 원인 코드, 했음이 아니면 하나 이상), 투입 인원
(모르면 비움), 장비·메모, 마지막 기록자·시각, 기록할 때의 작업 날짜·계획 버전.

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "work_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="CASCADE"),
                  nullable=False),  # fmt: skip
        sa.Column("work_item_id", sa.Integer(),
                  sa.ForeignKey("work_items.id", ondelete="CASCADE"), nullable=False,
                  unique=True),  # fmt: skip
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("plan_version", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(12), nullable=False),
        sa.Column("causes", sa.ARRAY(sa.String(20)), nullable=False, server_default="{}"),
        sa.Column("workers", sa.Integer(), nullable=True),
        sa.Column("equipment_note", sa.String(120), nullable=False, server_default=""),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("recorded_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("outcome IN ('done', 'partial', 'not_done')",
                           name="ck_work_reports_outcome"),  # fmt: skip
        sa.CheckConstraint("outcome = 'done' OR cardinality(causes) >= 1",
                           name="ck_work_reports_cause"),  # fmt: skip
        sa.CheckConstraint("workers IS NULL OR workers BETWEEN 0 AND 999",
                           name="ck_work_reports_workers"),  # fmt: skip
        sa.CheckConstraint("char_length(note) <= 500", name="ck_work_reports_note"),
    )
    op.create_index("ix_work_reports_site_date", "work_reports", ["site_id", "work_date"])


def downgrade() -> None:
    op.drop_index("ix_work_reports_site_date", table_name="work_reports")
    op.drop_table("work_reports")
