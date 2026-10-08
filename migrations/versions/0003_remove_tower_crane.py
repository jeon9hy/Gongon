"""현장 공종에서 타워크레인 운전 제거(D-032)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-08
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 목록에서만 빼면 이미 고른 현장에 '기준 확인 전 → 확인 필요'가 계속 뜬다.
    # 저장된 판정 내역은 그대로 둔다. 타워크레인만 골랐던 현장은 공종이 비고 공통(폭염)
    # 판정만 받는다. 다른 공종을 지어내 채우지 않는다.
    op.execute("UPDATE sites SET work_types = array_remove(work_types, '타워크레인 운전')")


def downgrade() -> None:
    # 어느 현장이 타워크레인을 골랐었는지 남기지 않으므로 되돌릴 수 없다.
    # 스키마 변경이 없어 할 일도 없다.
    pass
