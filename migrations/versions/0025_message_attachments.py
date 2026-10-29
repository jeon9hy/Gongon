"""대화방 첨부 (D-111)

메시지 하나에 첨부 하나: 사진(보관 키·종류·크기), 연락처(명부 담당자), 조치. 변경 건은 기존 linked_case_id.
연락처·조치가 지워져도 메시지는 남는다(SET NULL). 사진만 보내면 글이 빈다. 첨부가 지워져 글 없는 메시지가
남아도 그 지우기가 막히지 않게 DB는 길이 상한만 지키고, '글이나 첨부 하나'는 서비스가 확인한다.

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_site_messages_body_length", "site_messages", type_="check")
    op.create_check_constraint(
        "ck_site_messages_body_length", "site_messages", "char_length(body) <= 1000"
    )
    op.add_column("site_messages", sa.Column("photo_key", sa.String(120), nullable=True))
    op.add_column("site_messages", sa.Column("photo_type", sa.String(20), nullable=True))
    op.add_column("site_messages", sa.Column("photo_bytes", sa.Integer(), nullable=True))
    op.add_column(
        "site_messages",
        sa.Column(
            "linked_contact_id",
            sa.Integer(),
            sa.ForeignKey("participant_contacts.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "site_messages",
        sa.Column(
            "linked_action_id",
            sa.Integer(),
            sa.ForeignKey("action_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_constraint("ck_site_messages_body_length", "site_messages", type_="check")
    op.create_check_constraint(
        "ck_site_messages_body_length", "site_messages", "char_length(body) BETWEEN 1 AND 1000"
    )
    for column in ("linked_action_id", "linked_contact_id", "photo_bytes", "photo_type", "photo_key"):
        op.drop_column("site_messages", column)
