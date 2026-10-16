"""참여 업체 명부·담당자 명부 (C04-9, D-066, collab-contract §2-1)

- project_participants를 넓힌다: 구분(협력업체·자재 공급·장비 임대·감리·CM), 맡은 공종,
  사업자번호(선택·검증 안 함), 참여 시작일, 참여 종료(시각·처리자), 등록자.
  기존 행은 값 없이 그대로 둔다(구분 NULL = 협력업체로 표시).
- 원청은 구분이 없고 참여 종료할 수 없다(CHECK).
- participant_contacts: 업체별 담당자 명부. 계정 없이 등록하고, 가입한 사람이면 user_id로 연결한다.
  같은 현장에서 한 사용자는 활성 연락처 하나에만 연결된다. 삭제는 removed_at(행 보존).

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("project_participants", sa.Column("category", sa.String(20), nullable=True))
    op.add_column("project_participants", sa.Column("trade_note", sa.String(60), nullable=True))
    op.add_column("project_participants", sa.Column("business_no", sa.String(20), nullable=True))
    op.add_column("project_participants", sa.Column("joined_on", sa.Date, nullable=True))
    op.add_column(
        "project_participants", sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "project_participants",
        sa.Column("ended_by_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
    )
    op.add_column(
        "project_participants",
        sa.Column("created_by_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_check_constraint(
        "ck_participants_category",
        "project_participants",
        "category IS NULL OR category IN ('subcontractor', 'supplier', 'equipment', 'supervision')",
    )
    op.create_check_constraint(
        "ck_participants_prime_fixed",
        "project_participants",
        "kind <> 'prime' OR (category IS NULL AND ended_at IS NULL)",
    )
    op.create_table(
        "participant_contacts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("site_id", sa.Integer, nullable=False),
        sa.Column("participant_id", sa.Integer, nullable=False),
        sa.Column("name", sa.String(40), nullable=False),
        sa.Column("job_title", sa.String(40), nullable=False, server_default=""),
        sa.Column("phone", sa.String(30), nullable=False, server_default=""),
        sa.Column("memo", sa.String(200), nullable=False, server_default=""),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_by_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["participant_id", "site_id"],
            ["project_participants.id", "project_participants.site_id"],
            name="fk_contacts_participant_site",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_contacts_participant", "participant_contacts", ["participant_id"])
    op.create_index(
        "uq_contacts_active_site_user",
        "participant_contacts",
        ["site_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("user_id IS NOT NULL AND removed_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_table("participant_contacts")
    op.drop_constraint("ck_participants_prime_fixed", "project_participants")
    op.drop_constraint("ck_participants_category", "project_participants")
    for column in (
        "created_by_user_id",
        "ended_by_user_id",
        "ended_at",
        "joined_on",
        "business_no",
        "trade_note",
        "category",
    ):
        op.drop_column("project_participants", column)
