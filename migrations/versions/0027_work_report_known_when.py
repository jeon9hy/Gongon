"""작업일보: 일부만·못함을 언제 알았나 (C14-5, D-113)

전날 · 당일 아침 · 현장 와서. 선택 항목이라 비울 수 있고, 했음이면 비운다.

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("work_reports", sa.Column("known_when", sa.String(12), nullable=True))
    op.create_check_constraint(
        "ck_work_reports_known_when",
        "work_reports",
        "known_when IS NULL OR (known_when IN ('day_before', 'morning', 'on_site') "
        "AND outcome <> 'done')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_work_reports_known_when", "work_reports", type_="check")
    op.drop_column("work_reports", "known_when")
