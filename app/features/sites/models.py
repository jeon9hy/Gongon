from datetime import date, datetime, time

from sqlalchemy import ARRAY, Date, DateTime, Float, Integer, String, Time, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(60))
    # 대표 주소: 도로명이 있으면 도로명, 없으면 지번(D-048). 예보구역·이름 대체에 쓴다.
    # 격자는 위경도로 정한다
    address: Mapped[str] = mapped_column(String(200), default="")
    road_address: Mapped[str] = mapped_column(String(200), default="", server_default="")
    lot_address: Mapped[str] = mapped_column(String(200), default="", server_default="")
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
    # 삭제한 현장(D-040). 판정 내역을 보관하려고 행은 남기고 목록·조회에서만 뺀다.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
