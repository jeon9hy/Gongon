"""현장 기본 공종·작업 시간을 쓰지 않는다 (C04-3, D-059)

공종·작업 시간은 작업 일정마다 정한다. 기존 값은 지우지 않고 남겨 두되(과거 판정은 공종 이름·작업 시각을
판정 행에 따로 저장해 영향 없음) 새 현장은 비워 둘 수 있게 NOT NULL을 푼다.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE sites ALTER COLUMN work_start_local DROP NOT NULL")
    op.execute("ALTER TABLE sites ALTER COLUMN work_end_local DROP NOT NULL")
    op.execute("ALTER TABLE sites ALTER COLUMN work_types DROP NOT NULL")
    op.execute("ALTER TABLE sites ALTER COLUMN work_types SET DEFAULT '{}'")


def downgrade() -> None:
    # 0013 이후 만든 현장은 값이 비어 있다. 예전 앱이 읽을 수 있게 그때의 기본값으로 채운다.
    op.execute("UPDATE sites SET work_start_local = '07:00' WHERE work_start_local IS NULL")
    op.execute("UPDATE sites SET work_end_local = '17:00' WHERE work_end_local IS NULL")
    op.execute("UPDATE sites SET work_types = '{}' WHERE work_types IS NULL")
    op.execute("ALTER TABLE sites ALTER COLUMN work_types DROP DEFAULT")
    op.execute("ALTER TABLE sites ALTER COLUMN work_types SET NOT NULL")
    op.execute("ALTER TABLE sites ALTER COLUMN work_end_local SET NOT NULL")
    op.execute("ALTER TABLE sites ALTER COLUMN work_start_local SET NOT NULL")
