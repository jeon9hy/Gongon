"""예보 수집과 재사용. 같은 발표 시각·격자는 한 번만 받아 여러 현장이 공유한다."""

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.features.forecasts.models import STATUS_FAILED, STATUS_SUCCESS, ForecastRun
from engine.forecast import (
    ForecastFetchError,
    HttpGet,
    fetch_vilage_forecast,
    latest_base_at,
    normalize,
)
from engine.forecast.kma import urllib_get
from engine.judgment import WeatherInput

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ForecastSnapshot:
    run_id: int
    base_at: datetime
    weather: WeatherInput | None  # 실패면 None
    failure_reason: str | None


def get_http_get() -> HttpGet:
    """FastAPI 의존성. 테스트에서 가짜 응답 함수로 바꾼다."""
    return urllib_get


def get_forecast(
    session: Session, nx: int, ny: int, now: datetime, service_key: str, http_get: HttpGet
) -> ForecastSnapshot:
    base_at = latest_base_at(now)
    cached = session.scalars(
        select(ForecastRun).where(
            ForecastRun.base_at == base_at,
            ForecastRun.grid_nx == nx,
            ForecastRun.grid_ny == ny,
            ForecastRun.status == STATUS_SUCCESS,
        )
    ).first()
    if cached is not None:
        return _snapshot(cached)

    try:
        fetched = fetch_vilage_forecast(service_key, base_at, nx, ny, http_get)
    except ForecastFetchError as error:
        logger.warning("예보 수집 실패 base_at=%s nx=%s ny=%s: %s", base_at, nx, ny, error)
        run = ForecastRun(
            base_at=base_at, grid_nx=nx, grid_ny=ny, status=STATUS_FAILED,
            failure_reason=str(error), raw_items=None,
        )  # fmt: skip
    else:
        run = ForecastRun(
            base_at=base_at, grid_nx=nx, grid_ny=ny, status=STATUS_SUCCESS,
            failure_reason=None, raw_items=list(fetched.items),
        )  # fmt: skip
    session.add(run)
    session.flush()
    return _snapshot(run)


def _snapshot(run: ForecastRun) -> ForecastSnapshot:
    if run.status != STATUS_SUCCESS or run.raw_items is None:
        return ForecastSnapshot(run.id, run.base_at, None, run.failure_reason or "수집 실패")
    return ForecastSnapshot(run.id, run.base_at, normalize(run.base_at, run.raw_items), None)
