"""재변경 조치 이어받기·열람 사건 (C07 일부, 계약 §6)

- action_items.carried_from_id: 재변경 제안 때 이전 확정 버전의 조치에서 만든 후보가 어느 조치를
  이어받았는지. 확정하면 이전 조치의 replaced_by_id가 이 새 조치를 가리킨다.
- action_events.kind에 'viewed'(열람)를 더한다. 담당자가 처음 열어 본 시각이며 상태는 바꾸지 않는다.

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_KINDS = ("requested", "accepted", "resumed", "blocked", "reported", "verified", "rejected",
             "excluded", "replaced", "phone_record")  # fmt: skip
NEW_KINDS = (*OLD_KINDS, "viewed")


def _in(values: tuple[str, ...]) -> str:
    return f"kind IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    op.add_column(
        "action_items",
        sa.Column(
            "carried_from_id",
            sa.Integer,
            sa.ForeignKey("action_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.drop_constraint("ck_action_events_kind", "action_events", type_="check")
    op.create_check_constraint("ck_action_events_kind", "action_events", _in(NEW_KINDS))


def downgrade() -> None:
    op.execute("DELETE FROM action_events WHERE kind = 'viewed'")
    op.drop_constraint("ck_action_events_kind", "action_events", type_="check")
    op.create_check_constraint("ck_action_events_kind", "action_events", _in(OLD_KINDS))
    op.drop_column("action_items", "carried_from_id")
