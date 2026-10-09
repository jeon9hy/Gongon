"""예보 수집과 재사용. 같은 발표 시각·격자(중기는 예보구역)는 한 번만 받아 현장들이 공유한다."""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.features.forecasts.models import (
    STATUS_FAILED,
    STATUS_SUCCESS,
    ForecastRun,
    MidForecastRun,
)
from engine.forecast import (
    ForecastFetchError,
    HttpGet,
    KmaAuth,
    MidLandForecast,
    fetch_mid_land,
    fetch_vilage_forecast,
    latest_base_at,
    latest_issue_at,
    normalize,
    parse_mid_land,
    previous_issue_at,
)
from engine.forecast.kma import rain_probability_by_hour, urllib_get
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
    session: Session, nx: int, ny: int, now: datetime, auth: KmaAuth, http_get: HttpGet
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
        fetched = fetch_vilage_forecast(auth, base_at, nx, ny, http_get)
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


@dataclass(frozen=True, slots=True)
class RunStatus:
    """가장 최근 수집 시도(홈의 데이터 상태 표시용)."""

    base_at: datetime
    requested_at: datetime
    succeeded: bool
    failure_reason: str | None


def latest_run(session: Session) -> RunStatus | None:
    run = session.scalars(
        select(ForecastRun).order_by(ForecastRun.requested_at.desc(), ForecastRun.id.desc())
    ).first()
    if run is None:
        return None
    return RunStatus(
        run.base_at, run.requested_at, run.status == STATUS_SUCCESS, run.failure_reason
    )


def latest_forecast_times(session: Session, nx: int, ny: int) -> list[datetime]:
    """이 격자의 가장 최근 성공 수집에 값이 있는 예보 시각(정렬). 수집 전이면 빈 목록."""
    run = session.scalars(
        select(ForecastRun)
        .where(
            ForecastRun.grid_nx == nx,
            ForecastRun.grid_ny == ny,
            ForecastRun.status == STATUS_SUCCESS,
        )
        .order_by(ForecastRun.base_at.desc(), ForecastRun.id.desc())
    ).first()
    snapshot = None if run is None else _snapshot(run)
    if snapshot is None or snapshot.weather is None:
        return []
    return sorted(h.valid_at for h in snapshot.weather.hours)


def rain_probability_by_run(
    session: Session, run_ids: Sequence[int]
) -> dict[int, dict[datetime, int]]:
    """수집별 강수확률(POP, %)을 예보 시각별로(쿼리 1회). 원자료가 없는 수집은 빠진다."""
    if not run_ids:
        return {}
    rows = session.execute(
        select(ForecastRun.id, ForecastRun.raw_items).where(
            ForecastRun.id.in_(set(run_ids)), ForecastRun.raw_items.is_not(None)
        )
    )
    # 실패한 수집은 raw_items가 JSON null로 저장될 수 있어 목록만 읽는다.
    return {
        run_id: rain_probability_by_hour(items) for run_id, items in rows if isinstance(items, list)
    }


def _snapshot(run: ForecastRun) -> ForecastSnapshot:
    if run.status != STATUS_SUCCESS or run.raw_items is None:
        return ForecastSnapshot(run.id, run.base_at, None, run.failure_reason or "수집 실패")
    return ForecastSnapshot(run.id, run.base_at, normalize(run.base_at, run.raw_items), None)


def get_mid_forecast(
    session: Session, region_id: str, now: datetime, service_key: str, http_get: HttpGet
) -> MidLandForecast | None:
    """중기육상예보. 최근 발표가 아직 제공 전이면 그 전 발표를 쓴다(제공 지연은 문서에 없음).

    실패는 시도마다 기록하고 None을 돌려준다. 주간 보기의 참고 정보라 판정 실행을 멈추지 않는다.
    """
    latest = latest_issue_at(now)
    for issued_at in (latest, previous_issue_at(latest)):
        cached = session.scalars(
            select(MidForecastRun).where(
                MidForecastRun.issued_at == issued_at,
                MidForecastRun.region_id == region_id,
                MidForecastRun.status == STATUS_SUCCESS,
            )
        ).first()
        if cached is not None and cached.raw_item is not None:
            return parse_mid_land(cached.issued_at, cached.raw_item)
        try:
            item = fetch_mid_land(service_key, issued_at, region_id, http_get)
        except ForecastFetchError as error:
            logger.warning("중기예보 수집 실패 tmFc=%s regId=%s: %s", issued_at, region_id, error)
            session.add(MidForecastRun(issued_at=issued_at, region_id=region_id,
                                       status=STATUS_FAILED, failure_reason=str(error),
                                       raw_item=None))  # fmt: skip
            session.flush()
            continue
        session.add(MidForecastRun(issued_at=issued_at, region_id=region_id,
                                   status=STATUS_SUCCESS, failure_reason=None,
                                   raw_item=item))  # fmt: skip
        session.flush()
        return parse_mid_land(issued_at, item)
    return None


def latest_mid_forecast(session: Session, region_id: str) -> MidLandForecast | None:
    """이 예보구역의 가장 최근 성공 수집(주간 보기용, 쿼리 1회)."""
    run = session.scalars(
        select(MidForecastRun)
        .where(MidForecastRun.region_id == region_id, MidForecastRun.status == STATUS_SUCCESS)
        .order_by(MidForecastRun.issued_at.desc(), MidForecastRun.id.desc())
    ).first()
    if run is None or run.raw_item is None:
        return None
    return parse_mid_land(run.issued_at, run.raw_item)
