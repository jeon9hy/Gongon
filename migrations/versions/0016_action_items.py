"""후속 조치·조치 사건·위임·변경 건 종료 (C06, collab-contract §5)

- 조치는 변경 버전에 묶인다. 영향 검토 중에는 후보(candidate)이고 확정과 같은 트랜잭션에서 requested가 된다.
- 상태: candidate → requested → accepted ⇄ blocked → reported → verified, 반려는 reported → accepted.
  replaced(재변경으로 대체)·excluded(조정자가 이유와 함께 제외)는 끝 상태다.
- 검증자는 완료 보고자와 다르다(A3). 기한이 없으면 미정 사유가 있어야 한다(A4).
- 사건(action_events)은 모든 상태 전이와 전화 확인 기록을 남긴다. 실제 처리 시각·기록 시각을 따로 둔다.
- 위임(action_delegations)은 같은 업체 안에서 기간을 정해 수행을 맡긴다.
- 담당은 계정(assignee_user_id) 또는 계정 없는 명부의 사람(assignee_contact_id, D-066) 중 하나다.
  명부의 사람이 응답하면 조정자가 전화로 확인해 대신 기록한다. done_criteria는 완료 기준(D-070).

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

STATUSES = ("candidate", "requested", "accepted", "blocked", "reported", "verified", "replaced",
            "excluded")  # fmt: skip
KINDS = ("requested", "accepted", "resumed", "blocked", "reported", "verified", "rejected",
         "excluded", "replaced", "phone_record")  # fmt: skip


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    op.add_column("change_revisions", sa.Column("no_action_reason", sa.Text, nullable=True))
    op.add_column(
        "change_cases",
        sa.Column("closed_by_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_table(
        "action_items",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "case_id", sa.Integer, sa.ForeignKey("change_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "revision_id", sa.Integer, sa.ForeignKey("change_revisions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("site_id", sa.Integer, nullable=False),
        sa.Column("title", sa.String(80), nullable=False),
        sa.Column("done_criteria", sa.String(120), nullable=False, server_default=""),
        sa.Column("performing_participant_id", sa.Integer, nullable=False),
        sa.Column("assignee_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "assignee_contact_id", sa.Integer, sa.ForeignKey("participant_contacts.id"),
            nullable=True,
        ),
        sa.Column("verifier_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("required", sa.Boolean, nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_note", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_by_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("blocked_reason", sa.Text, nullable=True),
        sa.Column("blocked_resolver", sa.String(60), nullable=True),
        sa.Column("reported_by_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("performed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_by_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("excluded_by_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("excluded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exclude_reason", sa.Text, nullable=True),
        sa.Column(
            "replaced_by_id", sa.Integer, sa.ForeignKey("action_items.id"), nullable=True
        ),  # C07에서 새 조치와 연결
        # 수행 업체는 같은 현장의 참여 업체여야 한다
        sa.ForeignKeyConstraint(
            ["performing_participant_id", "site_id"],
            ["project_participants.id", "project_participants.site_id"],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(_in("status", STATUSES), name="ck_action_items_status"),
        sa.CheckConstraint(
            "due_at IS NOT NULL OR coalesce(due_note, '') <> ''", name="ck_action_items_due"
        ),
        sa.CheckConstraint(
            "assignee_user_id IS NULL OR assignee_contact_id IS NULL",
            name="ck_action_items_one_assignee",
        ),
        sa.CheckConstraint(
            "assignee_user_id IS NULL OR assignee_user_id <> verifier_user_id",
            name="ck_action_items_assignee_not_verifier",
        ),
        sa.CheckConstraint(
            "status <> 'blocked' OR (coalesce(blocked_reason, '') <> ''"
            " AND coalesce(blocked_resolver, '') <> '')",
            name="ck_action_items_blocked_reason",
        ),
        sa.CheckConstraint(
            "status <> 'reported' OR (reported_by_user_id IS NOT NULL AND performed_at IS NOT NULL)",
            name="ck_action_items_reported",
        ),
        sa.CheckConstraint(
            "status <> 'verified' OR (verified_by_user_id IS NOT NULL"
            " AND verified_by_user_id <> reported_by_user_id)",
            name="ck_action_items_verifier_not_reporter",
        ),
        sa.CheckConstraint(
            "status <> 'excluded' OR coalesce(exclude_reason, '') <> ''",
            name="ck_action_items_exclude_reason",
        ),
    )
    op.create_index("ix_action_items_revision", "action_items", ["revision_id"])
    op.create_index("ix_action_items_site_status", "action_items", ["site_id", "status"])
    op.create_table(
        "action_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "action_id", sa.Integer, sa.ForeignKey("action_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "revision_id", sa.Integer, sa.ForeignKey("change_revisions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("actor_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        # 수행자 대신 조정자가 전화로 확인해 기록함
        sa.Column("on_behalf", sa.Boolean, nullable=False, server_default=sa.false()),
        # 위임받아 처리함(원래 담당자)
        sa.Column(
            "delegated_from_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True
        ),
        sa.Column("performed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("body", sa.Text, nullable=False, server_default=""),
        sa.Column("counterpart", sa.String(100), nullable=False, server_default=""),
        sa.Column("reference", sa.String(100), nullable=False, server_default=""),
        sa.Column("contacted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(_in("kind", KINDS), name="ck_action_events_kind"),
        sa.CheckConstraint(
            "NOT on_behalf OR (counterpart <> '' AND contacted_at IS NOT NULL)",
            name="ck_action_events_on_behalf_contact",
        ),
    )
    op.create_index("ix_action_events_action", "action_events", ["action_id", "id"])
    op.create_table(
        "action_delegations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "site_id", sa.Integer, sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("from_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("to_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.CheckConstraint("from_user_id <> to_user_id", name="ck_action_delegations_other"),
        sa.CheckConstraint("starts_at < ends_at", name="ck_action_delegations_period"),
    )
    op.create_index("ix_action_delegations_site", "action_delegations", ["site_id", "to_user_id"])


def downgrade() -> None:
    op.drop_table("action_delegations")
    op.drop_table("action_events")
    op.drop_table("action_items")
    op.drop_column("change_cases", "closed_by_user_id")
    op.drop_column("change_revisions", "no_action_reason")
