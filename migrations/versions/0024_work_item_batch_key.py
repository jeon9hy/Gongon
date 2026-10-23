"""작업 등록 묶음 (D-098, C04-43)

여러 날·여러 작업을 한 번에 추가했거나 공정표 한 파일로 넣은 작업에 같은 묶음 키를 둔다.
지울 때 함께 등록한 남은 작업을 한꺼번에 지우는 데 쓴다. 기존 작업은 묶음 없음(None)으로 둔다.

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("work_items", sa.Column("batch_key", sa.String(32), nullable=True))
    op.create_index("ix_work_items_site_batch", "work_items", ["site_id", "batch_key"])


def downgrade() -> None:
    op.drop_index("ix_work_items_site_batch", table_name="work_items")
    op.drop_column("work_items", "batch_key")
