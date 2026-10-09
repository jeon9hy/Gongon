"""판정 내역 묶음: 대상 날짜 → 현장(작업별 최신 판정만, repository.page)."""

from datetime import date, datetime

import pytest

from app.features.judgments.models import Judgment
from app.features.judgments.service import _history_days, page_window
from engine.kst import KST


def judgment(
    judgment_id: int, site_id: int, target: date, work_type: str = "철골 작업"
) -> Judgment:
    return Judgment(
        id=judgment_id,
        site_id=site_id,
        target_date=target,
        work_type=work_type,
        work_item_id=None,
        work_start_at=datetime(target.year, target.month, target.day, 7, tzinfo=KST),
        work_end_at=datetime(target.year, target.month, target.day, 17, tzinfo=KST),
        verdict="진행",
        rule_version="v1",
        forecast_issued_at=datetime(2026, 10, 4, 17, tzinfo=KST),
        failure_reason=None,
    )


def test_rows_are_grouped_by_date_then_site() -> None:
    oct6, oct5 = date(2026, 10, 6), date(2026, 10, 5)
    rows = [  # repository.page 순서: 날짜 내림차순 → 현장
        judgment(1, 1, oct6),
        judgment(2, 1, oct6, work_type="콘크리트 타설"),
        judgment(3, 2, oct6),
        judgment(4, 1, oct5),
    ]

    days = _history_days(rows, {1: "○○현장"})

    assert [(d.label, d.count) for d in days] == [("10월 6일(화)", 3), ("10월 5일(월)", 1)]
    assert [s.site_name for s in days[0].sites] == ["○○현장", "삭제된 현장"]
    assert [r.judgment_id for r in days[0].sites[0].rows] == [1, 2]


@pytest.mark.parametrize(
    ("page", "last", "expected"),
    [
        (1, 1, [1]),
        (1, 5, [1, 2, 3, 4, 5]),  # 한 쪽만 비면 '…' 대신 그 쪽
        (1, 10, [1, 2, 3, None, 10]),
        (6, 10, [1, None, 4, 5, 6, 7, 8, 9, 10]),
        (5, 12, [1, 2, 3, 4, 5, 6, 7, None, 12]),  # 1과 3 사이 한 쪽(2)은 그대로
        (12, 12, [1, None, 10, 11, 12]),
    ],
)
def test_page_window_shows_first_last_and_two_around(
    page: int, last: int, expected: list[int | None]
) -> None:
    assert page_window(page, last) == expected
