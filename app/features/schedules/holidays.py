"""달력 공휴일(한국천문연구원 특일 정보). 해마다 한 번 받아 이 프로세스에 기억한다.

공휴일은 판정에 쓰지 않고 달력 표시만 한다. 받지 못하면 공휴일 없이 보이고(작업 표시는 그대로),
같은 실패로 매 화면마다 다시 부르지 않게 한 시간 동안은 다시 시도하지 않는다.
"""

import logging
from collections.abc import Callable, Mapping
from datetime import date, datetime, timedelta
from typing import Annotated

from fastapi import Depends

from app.core.config import Settings, get_settings
from app.features.forecasts.service import get_http_get
from engine.forecast import HttpGet
from engine.holidays import HolidayFetchError, fetch_holidays
from engine.kst import KST

logger = logging.getLogger(__name__)

KEEP_OK = timedelta(days=1)  # 임시공휴일이 새로 지정될 수 있어 하루에 한 번은 다시 받는다
KEEP_FAILED = timedelta(hours=1)

HolidayLookup = Callable[[int], Mapping[date, str]]
_cache: dict[int, tuple[datetime, dict[date, str]]] = {}


def clear_cache() -> None:
    _cache.clear()


def lookup_with(http_get: HttpGet, service_key: str) -> HolidayLookup:
    def holidays_of(year: int) -> Mapping[date, str]:
        now = datetime.now(KST)
        cached = _cache.get(year)
        if cached is not None and now < cached[0]:
            return cached[1]
        try:
            days = fetch_holidays(service_key, year, http_get)
            _cache[year] = (now + KEEP_OK, days)
        except HolidayFetchError as error:
            logger.warning("%s년 공휴일을 받지 못함: %s", year, error)
            days = cached[1] if cached is not None else {}  # 이전에 받은 값이 있으면 그대로 쓴다
            _cache[year] = (now + KEEP_FAILED, days)
        return days

    return holidays_of


def get_holiday_lookup(
    http_get: Annotated[HttpGet, Depends(get_http_get)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> HolidayLookup:
    """FastAPI 의존성. 테스트에서는 get_http_get·get_settings가 가짜로 바뀐다."""
    return lookup_with(http_get, settings.kma_service_key)


HolidayLookupDep = Annotated[HolidayLookup, Depends(get_holiday_lookup)]
