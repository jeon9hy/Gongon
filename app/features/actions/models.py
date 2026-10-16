from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, ForeignKeyConstraint, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ActionItem(Base):
    """변경 버전에 묶인 후속 조치(C06). 확정 뒤에는 상태·처리 기록만 바뀌고 내용은 고치지 않는다."""

    __tablename__ = "action_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["performing_participant_id", "site_id"],
            ["project_participants.id", "project_participants.site_id"],
            ondelete="CASCADE",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("change_cases.id", ondelete="CASCADE"))
    revision_id: Mapped[int] = mapped_column(ForeignKey("change_revisions.id", ondelete="CASCADE"))
    site_id: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(80))
    done_criteria: Mapped[str] = mapped_column(String(120), default="")  # 완료 기준(D-070)
    performing_participant_id: Mapped[int] = mapped_column(Integer)
    assignee_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    # 계정 없는 명부의 사람(D-066). 응답은 조정자가 전화로 확인해 대신 기록한다
    assignee_contact_id: Mapped[int | None] = mapped_column(ForeignKey("participant_contacts.id"))
    verifier_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    required: Mapped[bool] = mapped_column(Boolean)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    blocked_reason: Mapped[str | None] = mapped_column(Text)
    blocked_resolver: Mapped[str | None] = mapped_column(String(60))
    reported_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    performed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    excluded_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    excluded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exclude_reason: Mapped[str | None] = mapped_column(Text)
    replaced_by_id: Mapped[int | None] = mapped_column(ForeignKey("action_items.id"))


class ActionEvent(Base):
    """조치 사건. 상태 전이와 전화 확인 기록을 지우지 않고 쌓는다."""

    __tablename__ = "action_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action_id: Mapped[int] = mapped_column(ForeignKey("action_items.id", ondelete="CASCADE"))
    revision_id: Mapped[int] = mapped_column(ForeignKey("change_revisions.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(20))
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    on_behalf: Mapped[bool] = mapped_column(Boolean, default=False)
    delegated_from_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    performed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    body: Mapped[str] = mapped_column(Text, default="")
    counterpart: Mapped[str] = mapped_column(String(100), default="")
    reference: Mapped[str] = mapped_column(String(100), default="")
    contacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ActionDelegation(Base):
    """같은 업체 안의 수행 위임. 기간 안에서만 효력이 있고 회수해도 행은 남긴다."""

    __tablename__ = "action_delegations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"))
    from_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    to_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
