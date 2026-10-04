"""현장 작업 기간(시작일·종료일)

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 이미 등록된 현장은 기간이 비어 있다(제한 없음). 화면에서는 저장할 때 필수로 받는다.
    op.add_column("sites", sa.Column("work_start_date", sa.Date(), nullable=True))
    op.add_column("sites", sa.Column("work_end_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("sites", "work_end_date")
    op.drop_column("sites", "work_start_date")
