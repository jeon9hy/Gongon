from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"


class ForecastRun(Base):
    """예보 수집 한 번. 성공하면 원자료를 그대로 보관하고, 실패하면 원인을 남긴다."""

    __tablename__ = "forecast_runs"
    __table_args__ = (
        # 같은 발표 시각·격자의 성공 수집은 하나만 둔다(현장마다 다시 수집하지 않음).
        Index(
            "uq_forecast_runs_success",
            "base_at",
            "grid_nx",
            "grid_ny",
            unique=True,
            postgresql_where=text("status = 'success'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    base_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # 예보 발표 시각
    grid_nx: Mapped[int] = mapped_column(Integer)
    grid_ny: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(10))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    raw_items: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class MidForecastRun(Base):
    """중기육상예보 수집 한 번(D-042). 같은 발표 시각·예보구역의 성공 수집은 하나만 둔다."""

    __tablename__ = "mid_forecast_runs"
    __table_args__ = (
        Index(
            "uq_mid_forecast_runs_success",
            "issued_at",
            "region_id",
            unique=True,
            postgresql_where=text("status = 'success'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # tmFc
    region_id: Mapped[str] = mapped_column(String(8))  # 중기육상예보구역 코드
    status: Mapped[str] = mapped_column(String(10))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    raw_item: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # 응답 item 원자료
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
