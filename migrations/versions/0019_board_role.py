"""게시(board) 역할 (C11, D-067)

- 현장 휴게실 TV·태블릿용 공용 계정. 그 현장의 게시 화면(/board/{site_id}) 하나만 연다.
  다른 화면은 기존 역할 범위(조정자·담당자·열람자)로만 열리므로 자동으로 막힌다.
- 조정자가 가입한 계정을 '게시' 역할로 추가하고 회수한다. 원청 참여 업체 아래에 둔다.

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_memberships_role", "project_memberships", type_="check")
    op.create_check_constraint(
        "ck_memberships_role",
        "project_memberships",
        "role IN ('coordinator', 'assignee', 'viewer', 'board')",
    )


def downgrade() -> None:
    # 되돌리면 게시 계정 참여는 지운다(공용 화면 계정이라 업무 기록이 없다)
    op.execute("DELETE FROM project_memberships WHERE role = 'board'")
    op.drop_constraint("ck_memberships_role", "project_memberships", type_="check")
    op.create_check_constraint(
        "ck_memberships_role",
        "project_memberships",
        "role IN ('coordinator', 'assignee', 'viewer')",
    )
