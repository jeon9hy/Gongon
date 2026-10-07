from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Judgment(Base):
    """예보로 낸 판정 한 건. 저장 후 수정하지 않고 새로 추가한다(당시 판단을 다시 볼 수 있게)."""

    __tablename__ = "judgments"
    __table_args__ = (
        Index("ix_judgments_site_target", "site_id", "target_date"),
        # 같은 예보·기준·위치·작업 시간이면 다시 저장하지 않는다. 수집 실패 건은 시도마다 남긴다.
        Index(
            "uq_judgments_reuse_key",
            "site_id",
            "target_date",
            "work_type",
            "forecast_issued_at",
            "rule_version",
            "grid_nx",
            "grid_ny",
            "work_start_at",
            "work_end_at",
            unique=True,
            postgresql_where=text("forecast_issued_at IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id"))
    target_date: Mapped[date] = mapped_column(Date)
    work_type: Mapped[str] = mapped_column(String(40))  # 공종 이름(예: 철골 작업)
    work_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    work_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    verdict: Mapped[str] = mapped_column(String(10))
    rule_version: Mapped[str] = mapped_column(String(40))
    rule_source: Mapped[str] = mapped_column(String(200))
    rule_source_verified: Mapped[bool] = mapped_column(Boolean)
    grid_nx: Mapped[int] = mapped_column(Integer)
    grid_ny: Mapped[int] = mapped_column(Integer)
    forecast_run_id: Mapped[int | None] = mapped_column(ForeignKey("forecast_runs.id"))
    forecast_issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    # 기존 JSONB 형식은 docs/schema.json의 hours·windows 정의와 같다.
    hours: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    windows: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)  # 같은 판정이 이어진 작업 구간
    judged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
