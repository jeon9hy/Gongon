"""참여 업체가 맡은 업종 (D-088, C04-32)

업종 이름은 작업 고르기의 업종 목록(app/core/work_kinds.WORK_TRADES)과 같은 글자다. 기존 업체는
빈 목록으로 시작하고 자유 입력 메모(trade_note)는 그대로 둔다.

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "project_participants",
        sa.Column(
            "work_trades",
            postgresql.ARRAY(sa.String(60)),
            nullable=False,
            server_default=sa.text("'{}'::varchar[]"),
        ),
    )


def downgrade() -> None:
    op.drop_column("project_participants", "work_trades")
