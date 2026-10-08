"""1시간마다 전체 현장 자동 판정(D-043).

단기예보는 3시간마다 발표되고 10분 뒤 제공된다. 매시 15분에 돌리면 새 발표를 1시간 안에 반영한다.
같은 예보면 저장된 예보·판정을 재사용하므로 외부 호출과 새 판정 행이 늘지 않는다.
앱 프로세스 안에서 도는 단순 반복이다. 여러 프로세스로 배포하면 중복 실행되므로 배포(S07) 때
외부 예약 실행으로 옮긴다.
"""

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import sessionmaker

from app.core.clock import now_kst
from app.core.config import get_settings
from app.core.db import get_engine
from app.features.forecasts import service as forecasts_service
from app.features.judgments import service

logger = logging.getLogger(__name__)

REFRESH_MINUTE = 15


def seconds_until_next(now: datetime) -> float:
    """다음 매시 REFRESH_MINUTE분까지 남은 초. 정각에 걸리면 한 시간 뒤."""
    target = now.replace(minute=REFRESH_MINUTE, second=0, microsecond=0)
    if target <= now:
        target += timedelta(hours=1)
    return (target - now).total_seconds()


def run_once() -> str:
    settings = get_settings()
    factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    with factory() as session:
        return service.run_all(
            session,
            now_kst(),
            settings.kma_auth(),
            forecasts_service.get_http_get(),
            settings.kma_service_key,
        )


async def run_hourly() -> None:
    """취소될 때까지 매시 반복. 실패해도 다음 시각에 다시 시도한다(원인은 수집 기록에 남는다)."""
    while True:
        await asyncio.sleep(seconds_until_next(now_kst()))
        try:
            result = await asyncio.to_thread(run_once)
        except Exception:
            logger.exception("자동 판정 실패")
        else:
            logger.info("자동 판정 결과 %s", result)
