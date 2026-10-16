"""변경 건·변경 버전 (C05, collab-contract §4)

- 변경 건은 현장의 작업 하나에 대한 변경 묶음이다. 재변경은 같은 건의 새 버전(number+1)이다.
- 버전 상태: draft → review → confirmed(→ 다음 확정 때 superseded) / withdrawn.
- 한 건에 진행 중(draft·review) 버전은 하나, 현재 확정 버전도 하나(부분 고유 인덱스).
- 확정은 계획 갱신과 한 트랜잭션이다(서비스). confirm_key는 같은 확정 요청의 재전송을 알아본다.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REASONS = (
    "schedule", "labor", "equipment", "material", "design", "quality",
    "safety", "area", "cost", "external", "weather",
)  # fmt: skip


def upgrade() -> None:
    op.create_table(
        "change_cases",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "site_id", sa.Integer, sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "work_item_id", sa.Integer, sa.ForeignKey("work_items.id"), nullable=False
        ),
        sa.Column("title", sa.String(80), nullable=False),
        sa.Column("created_by_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_change_cases_site", "change_cases", ["site_id", "id"])
    reason_list = ", ".join(f"'{r}'" for r in REASONS)
    op.create_table(
        "change_revisions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "case_id",
            sa.Integer,
            sa.ForeignKey("change_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("number", sa.Integer, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("reasons", ARRAY(sa.String(20)), nullable=False),
        sa.Column("basis_note", sa.Text, nullable=False, server_default=""),
        sa.Column("based_on_plan_version", sa.Integer, nullable=False),
        # 변경 전(제안 당시 계획)과 변경 후 값
        sa.Column("before_work_date", sa.Date, nullable=False),
        sa.Column("before_start_local", sa.Time, nullable=False),
        sa.Column("before_end_local", sa.Time, nullable=False),
        sa.Column("before_location", sa.String(60), nullable=False),
        sa.Column("after_work_date", sa.Date, nullable=False),
        sa.Column("after_start_local", sa.Time, nullable=False),
        sa.Column("after_end_local", sa.Time, nullable=False),
        sa.Column("after_location", sa.String(60), nullable=False),
        sa.Column("proposed_by_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("proposed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_by_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirm_key", sa.String(64), nullable=True, unique=True),
        sa.Column("withdrawn_by_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdraw_reason", sa.Text, nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("case_id", "number", name="uq_change_revisions_number"),
        sa.CheckConstraint(
            "status IN ('draft', 'review', 'confirmed', 'superseded', 'withdrawn')",
            name="ck_change_revisions_status",
        ),
        sa.CheckConstraint(
            f"cardinality(reasons) >= 1 AND reasons <@ ARRAY[{reason_list}]::varchar[]",
            name="ck_change_revisions_reasons",
        ),
        sa.CheckConstraint(
            "after_start_local < after_end_local", name="ck_change_revisions_after_range"
        ),
        sa.CheckConstraint(
            "status <> 'confirmed' OR (confirmed_at IS NOT NULL AND confirmed_by_user_id IS NOT NULL)",
            name="ck_change_revisions_confirmed_by",
        ),
        sa.CheckConstraint(
            "status <> 'withdrawn' OR (withdrawn_at IS NOT NULL AND withdraw_reason <> '')",
            name="ck_change_revisions_withdraw_reason",
        ),
    )
    op.create_index(
        "uq_change_revisions_one_open",
        "change_revisions",
        ["case_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('draft', 'review')"),
    )
    op.create_index(
        "uq_change_revisions_one_current",
        "change_revisions",
        ["case_id"],
        unique=True,
        postgresql_where=sa.text("status = 'confirmed'"),
    )


def downgrade() -> None:
    op.drop_table("change_revisions")
    op.drop_table("change_cases")
