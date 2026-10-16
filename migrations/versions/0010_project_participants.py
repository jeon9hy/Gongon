"""현장(프로젝트) 참여 업체·멤버십·역할 (C03-2, D-057)

- 참여 업체는 현장당 회사 하나에 한 행, 원청(prime)은 현장당 하나.
- 멤버십의 site_id는 참여 업체의 site_id와 같아야 한다(복합 FK로 강제).
- 활성 멤버십(revoked_at IS NULL)은 (현장, 사용자)당 하나. 회수해도 행은 남긴다.
- 기존 현장에는 참여 업체를 만들지 않는다. 소유자를 추정하지 않고 scripts/grant_site.py로 지정한다.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project_participants",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "site_id", sa.Integer, sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "organization_id", sa.Integer, sa.ForeignKey("organizations.id"), nullable=False
        ),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("kind IN ('prime', 'subcontractor')", name="ck_participants_kind"),
        sa.UniqueConstraint("site_id", "organization_id", name="uq_participants_site_org"),
        sa.UniqueConstraint("id", "site_id", name="uq_participants_id_site"),
    )
    op.create_index(
        "uq_participants_one_prime",
        "project_participants",
        ["site_id"],
        unique=True,
        postgresql_where=sa.text("kind = 'prime'"),
    )
    op.create_table(
        "project_memberships",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("site_id", sa.Integer, nullable=False),
        sa.Column("participant_id", sa.Integer, nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("granted_by_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.CheckConstraint(
            "role IN ('coordinator', 'assignee', 'viewer')", name="ck_memberships_role"
        ),
        sa.ForeignKeyConstraint(
            ["participant_id", "site_id"],
            ["project_participants.id", "project_participants.site_id"],
            name="fk_memberships_participant_site",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "uq_memberships_active_site_user",
        "project_memberships",
        ["site_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index("ix_memberships_user", "project_memberships", ["user_id"])


def downgrade() -> None:
    op.drop_table("project_memberships")
    op.drop_table("project_participants")
