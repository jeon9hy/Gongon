"""작업 일정(work_items)과 판정의 작업 연결(S08-1, D-036)

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_REUSE_COLUMNS = (
    "site_id, target_date, work_type, forecast_issued_at, rule_version, "
    "grid_nx, grid_ny, work_start_at, work_end_at"
)


def upgrade() -> None:
    op.create_table(
        "work_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("work_type", sa.String(40), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("start_local", sa.Time(), nullable=False),
        sa.Column("end_local", sa.Time(), nullable=False),
        sa.Column("location", sa.String(60), nullable=False),
        sa.Column("memo", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_work_items_site_date", "work_items", ["site_id", "work_date"])
    # 작업을 지워도 당시 판정 기록은 남긴다(연결만 끊는다).
    op.add_column(
        "judgments",
        sa.Column(
            "work_item_id",
            sa.Integer(),
            sa.ForeignKey("work_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    # 같은 시간·공종의 작업이 둘이어도 따로 판정하도록 재사용 키에 작업을 넣는다.
    # NULL은 서로 다르게 취급되므로 현장 기본 시간 판정(작업 없음)은 0으로 묶는다.
    op.drop_index("uq_judgments_reuse_key", table_name="judgments")
    op.execute(
        f"CREATE UNIQUE INDEX uq_judgments_reuse_key ON judgments ({_REUSE_COLUMNS}, "
        "(coalesce(work_item_id, 0))) WHERE forecast_issued_at IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_index("uq_judgments_reuse_key", table_name="judgments")
    op.drop_column("judgments", "work_item_id")
    op.execute(
        f"CREATE UNIQUE INDEX uq_judgments_reuse_key ON judgments ({_REUSE_COLUMNS}) "
        "WHERE forecast_issued_at IS NOT NULL"
    )
    op.drop_index("ix_work_items_site_date", table_name="work_items")
    op.drop_table("work_items")
