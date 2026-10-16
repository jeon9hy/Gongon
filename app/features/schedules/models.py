from datetime import date, datetime, time

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text, Time, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class WorkItem(Base):
    """예정된 작업 한 건(현장·공종·날짜·시간). 예보로 자동 변경하지 않는다(product.md §4)."""

    __tablename__ = "work_items"
    __table_args__ = (Index("ix_work_items_site_date", "site_id", "work_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"))
    work_type: Mapped[str] = mapped_column(String(40))
    work_date: Mapped[date] = mapped_column(Date)  # 현장 현지 날짜(KST)
    start_local: Mapped[time] = mapped_column(Time)
    end_local: Mapped[time] = mapped_column(Time)
    location: Mapped[str] = mapped_column(String(60), default="")  # 작업 위치(예: A구역). 선택
    memo: Mapped[str] = mapped_column(Text, default="")
    # 지운 작업(C04-1). 판정과 당시 작업의 연결을 보존하려고 행은 남기고 목록·판정에서만 뺀다.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 실행 업체: 같은 현장의 참여 업체(0012 복합 FK). None은 미지정(기존 작업은 추정하지 않는다).
    performing_participant_id: Mapped[int | None] = mapped_column(Integer)
    # 계획 버전(1부터). 계획을 바꿀 때마다 1 올리고 이전 값은 WorkItemRevision에 남긴다.
    plan_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorkItemRevision(Base):
    """바뀌기 전 계획 한 벌. 행을 고치거나 지우지 않는다(C04-2)."""

    __tablename__ = "work_item_revisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    work_item_id: Mapped[int] = mapped_column(ForeignKey("work_items.id", ondelete="CASCADE"))
    plan_version: Mapped[int] = mapped_column(Integer)  # 이 값들이 유효했던 버전
    work_date: Mapped[date] = mapped_column(Date)
    start_local: Mapped[time] = mapped_column(Time)
    end_local: Mapped[time] = mapped_column(Time)
    location: Mapped[str] = mapped_column(String(60))
    memo: Mapped[str] = mapped_column(Text)
    performing_participant_id: Mapped[int | None] = mapped_column(Integer)
    changed_by_user_id: Mapped[int | None] = mapped_column(Integer)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(20))  # edit: 작업 일정 화면
