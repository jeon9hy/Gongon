"""사용자 휴대폰 번호 (C04-13, D-073)

- 가입 때 휴대폰 번호를 받고, 조정자가 그 번호로 사람을 찾아 현장에 추가한다.
- 번호는 숫자만(01012345678) 저장하고 사용자마다 하나, 사람마다 다르다(부분 고유 인덱스).
- 시제품 동안 문자 인증은 하지 않는다. phone_verified_at은 인증을 붙일 때 채우며 지금은 늘 NULL이다.
  기존 사용자는 번호 없이 두고(값을 지어내지 않음) 내 정보에서 등록한다.

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("phone", sa.String(20), nullable=True))
    op.add_column(
        "users", sa.Column("phone_verified_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_check_constraint("ck_users_phone_digits", "users", "phone ~ '^01[0-9]{8,9}$'")
    op.create_index(
        "uq_users_phone",
        "users",
        ["phone"],
        unique=True,
        postgresql_where=sa.text("phone IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_users_phone", table_name="users")
    op.drop_constraint("ck_users_phone_digits", "users", type_="check")
    op.drop_column("users", "phone_verified_at")
    op.drop_column("users", "phone")
