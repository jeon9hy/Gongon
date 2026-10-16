"""작업 삭제를 숨김 처리로 바꾼다 (C04-1, S08-4-2)

행을 지우면 judgments.work_item_id가 NULL(ON DELETE SET NULL)이 되고, 같은 공종·시간 작업의 판정이
재사용 키 `coalesce(work_item_id, 0)`에서 서로 겹쳐 두 번째 삭제가 고유 키 위반(500)이 됐다.
행을 남기면 판정과 당시 작업의 연결도 보존된다(현장 삭제 D-040과 같은 방식). 기존 행은 삭제되지 않은 상태다.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("work_items", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    # 숨긴 작업은 되돌릴 때 실제로 지운다(이전 스키마에는 숨김 상태가 없다). 판정 연결은 NULL이 된다.
    # 같은 공종·시간 작업 둘 이상을 숨겼으면 예전 충돌이 다시 나 되돌리기가 실패하고 전체가 롤백된다.
    op.execute("DELETE FROM work_items WHERE deleted_at IS NOT NULL")
    op.drop_column("work_items", "deleted_at")
