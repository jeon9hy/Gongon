from datetime import date, datetime, time

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text, Time, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class WorkItem(Base):
    """예정된 작업 한 건(현장·공종·날짜·시간). 예보로 자동 변경하지 않는다(총정리 §1 원칙)."""

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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
