"""현장 참여 코드 (D-095, C04-39)

현장마다 코드 하나. 이미 있는 현장(삭제한 현장 포함)에도 코드를 만들어 둔다. 삭제한 현장의
코드로는 참여할 수 없다(앱이 현장을 다시 확인한다).

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-23
"""

import secrets
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def upgrade() -> None:
    op.create_table(
        "site_join_codes",
        sa.Column(
            "site_id", sa.Integer, sa.ForeignKey("sites.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("code", sa.String(8), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.Integer, sa.ForeignKey("users.id")),
    )
    bind = op.get_bind()
    site_ids = [row[0] for row in bind.execute(sa.text("SELECT id FROM sites ORDER BY id"))]
    used: set[str] = set()
    rows = []
    for site_id in site_ids:
        code = ""
        while not code or code in used:
            code = "".join(secrets.choice(ALPHABET) for _ in range(8))
        used.add(code)
        rows.append({"site_id": site_id, "code": code})
    if rows:
        bind.execute(
            sa.text(
                "INSERT INTO site_join_codes (site_id, code, created_at) "
                "VALUES (:site_id, :code, now())"
            ),
            rows,
        )


def downgrade() -> None:
    op.drop_table("site_join_codes")
