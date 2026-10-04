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
