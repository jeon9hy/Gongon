from datetime import date, datetime

from sqlalchemy import ARRAY, Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class WorkReport(Base):
    """작업 한 건의 실제 결과(작업일보, C14-2·D-112).

    예보·판정·변경과 따로 저장하는 실제 작업 기록이다.

    작업 하나에 한 행이고 고치면 마지막 기록자·시각으로 바뀐다. 기록 뒤 계획이 바뀌었는지는
    plan_version으로 안다(기록을 새 계획으로 자동 승계하지 않는다).
    """

    __tablename__ = "work_reports"
    __table_args__ = (Index("ix_work_reports_site_date", "site_id", "work_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"))
    work_item_id: Mapped[int] = mapped_column(
        ForeignKey("work_items.id", ondelete="CASCADE"), unique=True
    )
    work_date: Mapped[date] = mapped_column(Date)  # 기록할 때 작업 날짜(KST)
    plan_version: Mapped[int] = mapped_column(Integer)  # 기록할 때 작업 계획 버전
    outcome: Mapped[str] = mapped_column(String(12))  # done · partial · not_done
    causes: Mapped[list[str]] = mapped_column(ARRAY(String(20)))  # 변경 원인과 같은 코드
    workers: Mapped[int | None] = mapped_column(
        Integer
    )  # 투입 인원. 모르면 None(0으로 채우지 않음)
    # 일부만·못함을 언제 알았나(D-113): day_before · morning · on_site, 모르면·했음이면 None
    known_when: Mapped[str | None] = mapped_column(String(12))
    equipment_note: Mapped[str] = mapped_column(String(120), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    recorded_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
