from datetime import date, datetime, time

from sqlalchemy import ARRAY, Date, DateTime, Float, Integer, String, Time, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(60))
    address: Mapped[str] = mapped_column(
        String(200), default=""
    )  # 필수 입력. 격자는 위경도로 정한다
    latitude_deg: Mapped[float] = mapped_column(Float)
    longitude_deg: Mapped[float] = mapped_column(Float)
    grid_nx: Mapped[int] = mapped_column(Integer)
    grid_ny: Mapped[int] = mapped_column(Integer)
    work_start_local: Mapped[time] = mapped_column(Time)  # 현장 현지 시각(KST)
    work_end_local: Mapped[time] = mapped_column(Time)
    work_types: Mapped[list[str]] = mapped_column(ARRAY(String(40)))
    # 작업 기간(현지 날짜, 양 끝 포함). 비어 있으면 기간 제한 없음(0002 이전에 등록한 현장).
    work_start_date: Mapped[date | None] = mapped_column(Date)
    work_end_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
