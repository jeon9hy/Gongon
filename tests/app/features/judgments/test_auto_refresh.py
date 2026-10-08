from datetime import datetime

import pytest

from app.features.judgments.auto_refresh import seconds_until_next
from engine.kst import KST


@pytest.mark.parametrize(
    ("now", "seconds"),
    [
        (datetime(2026, 10, 8, 14, 14, 59, tzinfo=KST), 1),
        (datetime(2026, 10, 8, 14, 15, 0, tzinfo=KST), 3600),  # 정각에 걸리면 한 시간 뒤
        (datetime(2026, 10, 8, 14, 30, 0, tzinfo=KST), 45 * 60),
        (datetime(2026, 10, 8, 23, 50, 0, tzinfo=KST), 25 * 60),  # 날짜가 바뀌어도
    ],
)
def test_seconds_until_next_quarter_past(now: datetime, seconds: float) -> None:
    assert seconds_until_next(now) == seconds
