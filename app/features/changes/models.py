from datetime import date, datetime, time

from sqlalchemy import ARRAY, Date, DateTime, ForeignKey, Integer, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ChangeCase(Base):
    """현장 작업 하나의 변경 묶음. 재변경은 같은 건에 새 버전을 쌓는다(C05)."""

    __tablename__ = "change_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"))
    work_item_id: Mapped[int] = mapped_column(ForeignKey("work_items.id"))
    title: Mapped[str] = mapped_column(String(80))
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # C06 종료
    closed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class ChangeRevision(Base):
    """변경 버전. 확정한 버전은 고치지 않는다(다음 확정 때 superseded로만 바뀐다)."""

    __tablename__ = "change_revisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("change_cases.id", ondelete="CASCADE"))
    number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))
    reasons: Mapped[list[str]] = mapped_column(ARRAY(String(20)))
    basis_note: Mapped[str] = mapped_column(Text, default="")
    based_on_plan_version: Mapped[int] = mapped_column(Integer)
    before_work_date: Mapped[date] = mapped_column(Date)
    before_start_local: Mapped[time] = mapped_column(Time)
    before_end_local: Mapped[time] = mapped_column(Time)
    before_location: Mapped[str] = mapped_column(String(60))
    after_work_date: Mapped[date] = mapped_column(Date)
    after_start_local: Mapped[time] = mapped_column(Time)
    after_end_local: Mapped[time] = mapped_column(Time)
    after_location: Mapped[str] = mapped_column(String(60))
    proposed_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    proposed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirm_key: Mapped[str | None] = mapped_column(String(64), unique=True)
    withdrawn_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withdraw_reason: Mapped[str | None] = mapped_column(Text)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 필수 후속 조치 없이 확정할 때의 이유(C06, 계약 §5)
    no_action_reason: Mapped[str | None] = mapped_column(Text)
