"""조치 입력 줄이기: 기한 미정 사유·보류를 풀 담당을 선택으로 (D-114)

기한이 없으면 사유가 없어도 ‘기한 미정’으로 둔다. 보류는 이유만 필수다.

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-30
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_action_items_due", "action_items", type_="check")
    op.drop_constraint("ck_action_items_blocked_reason", "action_items", type_="check")
    op.create_check_constraint(
        "ck_action_items_blocked_reason",
        "action_items",
        "status <> 'blocked' OR coalesce(blocked_reason, '') <> ''",
    )


def downgrade() -> None:
    # 되돌리기 전에 비어 있는 값을 채운다(이전 제약은 둘 다 필수였다)
    op.execute(
        "UPDATE action_items SET due_note = '기한 미정' "
        "WHERE due_at IS NULL AND coalesce(due_note, '') = ''"
    )
    op.execute(
        "UPDATE action_items SET blocked_resolver = '미정' "
        "WHERE status = 'blocked' AND coalesce(blocked_resolver, '') = ''"
    )
    op.drop_constraint("ck_action_items_blocked_reason", "action_items", type_="check")
    op.create_check_constraint(
        "ck_action_items_blocked_reason",
        "action_items",
        "status <> 'blocked' OR (coalesce(blocked_reason, '') <> ''"
        " AND coalesce(blocked_resolver, '') <> '')",
    )
    op.create_check_constraint(
        "ck_action_items_due", "action_items", "due_at IS NOT NULL OR coalesce(due_note, '') <> ''"
    )
