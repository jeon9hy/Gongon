"""작업 실행 업체·계획 버전·변경 이력 (C04-2, collab-contract §3)

- 실행 업체는 같은 현장의 참여 업체만(복합 FK). 기존 작업은 추정하지 않고 NULL(미지정)이다.
- plan_version은 1부터. 계획(날짜·시간·위치·메모·실행 업체)을 바꿀 때마다 1 올리고, 바뀌기 전 값을
  work_item_revisions에 남긴다. 저장할 때 제출한 버전과 현재 버전이 다르면 저장하지 않는다(서비스).
- 참여 업체 행이 지워지면(현장 삭제 CASCADE) 실행 업체 칸만 NULL이 된다(PostgreSQL 15+ 열 지정 SET NULL).

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "work_items", sa.Column("performing_participant_id", sa.Integer, nullable=True)
    )
    op.add_column(
        "work_items",
        sa.Column("plan_version", sa.Integer, nullable=False, server_default="1"),
    )
    op.execute(
        "ALTER TABLE work_items ADD CONSTRAINT fk_work_items_performing_participant "
        "FOREIGN KEY (performing_participant_id, site_id) "
        "REFERENCES project_participants (id, site_id) "
        "ON DELETE SET NULL (performing_participant_id)"
    )
    op.create_check_constraint("ck_work_items_plan_version", "work_items", "plan_version >= 1")
    op.create_table(
        "work_item_revisions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "work_item_id",
            sa.Integer,
            sa.ForeignKey("work_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # 이 행이 보존하는 '바뀌기 전' 버전 번호와 그때의 값
        sa.Column("plan_version", sa.Integer, nullable=False),
        sa.Column("work_date", sa.Date, nullable=False),
        sa.Column("start_local", sa.Time, nullable=False),
        sa.Column("end_local", sa.Time, nullable=False),
        sa.Column("location", sa.String(60), nullable=False),
        sa.Column("memo", sa.Text, nullable=False),
        sa.Column("performing_participant_id", sa.Integer, nullable=True),
        sa.Column("changed_by_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        # 'edit'(작업 일정 화면). C05의 변경 확정은 다른 값을 쓴다.
        sa.Column("source", sa.String(20), nullable=False),
        sa.UniqueConstraint("work_item_id", "plan_version", name="uq_work_item_revisions_version"),
    )


def downgrade() -> None:
    op.drop_table("work_item_revisions")
    op.drop_constraint("ck_work_items_plan_version", "work_items", type_="check")
    op.drop_constraint("fk_work_items_performing_participant", "work_items", type_="foreignkey")
    op.drop_column("work_items", "plan_version")
    op.drop_column("work_items", "performing_participant_id")
