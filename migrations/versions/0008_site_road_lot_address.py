"""현장 주소를 도로명·지번 두 칸으로 저장한다(D-048)

기존 address는 대표 주소(도로명 우선)로 남긴다. 기존 행은 형태로 나눠 옮긴다:
'○○로 12'·'○○길 3'처럼 로/길 뒤에 띄우고 번호가 오면 도로명, 아니면 지번.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for column in ("road_address", "lot_address"):
        op.add_column("sites", sa.Column(column, sa.String(200), nullable=False, server_default=""))
    # '태평로1가 31'(지번, 법정동 이름에 '로'가 붙음)과 구분하려고 로/길 뒤 공백을 요구한다.
    op.execute(r"UPDATE sites SET road_address = address WHERE address ~ '(로|길)\s+[0-9]'")
    op.execute("UPDATE sites SET lot_address = address WHERE road_address = ''")


def downgrade() -> None:
    op.drop_column("sites", "lot_address")
    op.drop_column("sites", "road_address")
