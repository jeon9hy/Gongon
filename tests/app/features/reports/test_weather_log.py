"""기상 작업중지 기록(C14-3, D-112). 가상 현장·가상 판정만 쓴다.

현재 시각은 2026-10-04(일) 15:00.
"""

from datetime import date, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.features.judgments.models import Judgment
from app.features.reports.models import WorkReport
from app.features.reports.service import month_start
from app.features.schedules.models import WorkItem
from engine.kst import KST
from tests.app.features.reports.test_daily import item, record, team, today_work, work_on
from tests.conftest import FIXED_NOW

__all__ = ["item", "team", "today_work"]


def log(client: TestClient, site_id: int, month: str = "") -> str:
    page = client.get(f"/reports/{site_id}/weather" + (f"?month={month}" if month else ""))
    assert page.status_code == 200, page.text
    return page.text


def judged(session: Session, w: WorkItem, verdict: str, at: datetime) -> None:
    session.add(
        Judgment(
            site_id=w.site_id, target_date=w.work_date, work_type=w.work_type,
            work_start_at=datetime.combine(w.work_date, w.start_local, KST),
            work_end_at=datetime.combine(w.work_date, w.end_local, KST),
            work_item_id=w.id, verdict=verdict, rule_version="test-v1", rule_source="[가상]",
            rule_source_verified=False, grid_nx=60, grid_ny=127, hours=[], windows=[],
            judged_at=at,
        )
    )  # fmt: skip
    session.commit()


@pytest.mark.parametrize(
    ("raw", "first"),
    [("", date(2026, 10, 1)), ("2026-11", date(2026, 11, 1)), ("2026-13", date(2026, 10, 1)),
     ("2026-12", date(2026, 12, 1)), ("abc", date(2026, 10, 1))],
)  # fmt: skip
def test_month_falls_back_to_this_month(raw: str, first: date) -> None:
    assert month_start(FIXED_NOW, raw) == first


def test_only_weather_caused_short_work_is_listed_with_the_last_verdict_before_start(
    client: TestClient, session: Session, item: WorkItem, today_work: WorkItem,
    team: dict[str, Any],
) -> None:  # fmt: skip
    other = work_on(client, session, item.site_id, "2026-10-04", "16:30", "18:00",
                    team["safety_company"])  # fmt: skip
    judged(session, today_work, "확인 필요", datetime(2026, 10, 3, 17, 0, tzinfo=KST))
    judged(session, today_work, "중지 검토", datetime(2026, 10, 4, 5, 0, tzinfo=KST))
    judged(session, today_work, "진행", datetime(2026, 10, 4, 16, 30, tzinfo=KST))  # 시작 뒤

    record(client, today_work, outcome="not_done", causes=["weather", "safety"], note="강풍")
    record(client, other, outcome="not_done", causes="material")  # 기상 아님
    page = log(client, item.site_id)

    assert "강풍" in page and "안전·작업 허가" in page
    assert "중지 검토" in page and "10/4(일) 05:00 판정" in page
    assert "진행</span>" not in page  # 작업 시작 뒤 판정은 붙이지 않는다
    assert "작업 2건 중 1건" in page and "전체 중지한 날</dt><dd>0일" in page

    record(client, other, outcome="not_done", causes="weather")  # 판정 없는 작업
    page = log(client, item.site_id)
    assert "판정 기록 없음" in page and "전체 중지" in page and "전체 중지한 날</dt><dd>1일" in page


def test_done_work_and_other_months_are_not_listed(
    client: TestClient, session: Session, today_work: WorkItem
) -> None:
    record(client, today_work, outcome="done", causes="weather")
    assert "기록이 없어요" in log(client, today_work.site_id)

    record(client, today_work, outcome="partial", causes="weather", note="오전만")
    # 다른 달 경계: 10/31은 10월, 11/1은 11월(같은 작업의 기록 날짜를 바꿔 확인)
    report = session.query(WorkReport).one()
    report.work_date = date(2026, 10, 31)
    session.commit()
    assert "오전만" in log(client, today_work.site_id, "2026-10")
    assert "오전만" not in log(client, today_work.site_id, "2026-11")
    report.work_date = date(2026, 11, 1)
    session.commit()
    assert "오전만" not in log(client, today_work.site_id, "2026-10")
    assert "오전만" in log(client, today_work.site_id, "2026-11")
