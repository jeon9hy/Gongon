"""현재 시각. FastAPI 의존성으로 받아 테스트에서 고정 시각으로 바꾼다."""

from datetime import datetime

from engine.kst import KST


def now_kst() -> datetime:
    return datetime.now(KST)
