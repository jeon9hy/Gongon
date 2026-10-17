"""현장 대화방 메시지 (C12, D-071)

- 현장마다 방 하나. 그 현장에 활성 멤버십이 있는 사람만 읽고 쓴다(권한은 teams 서비스).
- 메시지는 지우지 않고 deleted_at으로 숨긴다. 수정·삭제가 조치 기록을 바꾸지 않는다.
- linked_case_id: 사람이 고른 관련 변경 건. 카드는 그때그때 현재 상태를 읽어 보인다
  (메시지 본문의 일정이 현재 확정안처럼 보이지 않게).

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "site_messages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "site_id", sa.Integer, sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("author_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column(
            "linked_case_id",
            sa.Integer,
            sa.ForeignKey("change_cases.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "char_length(body) BETWEEN 1 AND 1000", name="ck_site_messages_body_length"
        ),
    )
    op.create_index("ix_site_messages_site_id", "site_messages", ["site_id", "id"])


def downgrade() -> None:
    op.drop_table("site_messages")
