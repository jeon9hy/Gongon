"""주간 작업계획표(C14-1, D-112). 가상 현장·가상 계정만 쓴다. 현재 시각은 2026-10-04(일) 15:00."""

from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.features.reports.service import week_start
from app.features.schedules.models import WorkItem
from tests.app.features.actions.test_actions import action, do, item, requested, team
from tests.app.features.changes.test_changes import OUTSIDER, VIEWER, join
from tests.conftest import FIXED_NOW, Browser

__all__ = ["item", "requested", "team"]  # 다른 시험 파일의 fixture를 이 파일에서 쓴다


def sheet(client: TestClient, site_id: int, start: str = "") -> str:
    page = client.get(f"/reports/{site_id}/weekly" + (f"?start={start}" if start else ""))
    assert page.status_code == 200, page.text
    return page.text


def add_work(client: TestClient, site_id: int, day: str, start: str, end: str, **form: Any) -> None:
    added = client.post(
        "/schedule",
        data={"site_id": site_id, "work_types": ["철골 작업"], "work_date": day,
              "work_dates": day, "start": start, "end": end, **form},
        follow_redirects=False,
    )  # fmt: skip
    assert added.status_code == 303, added.text


@pytest.mark.parametrize(
    ("requested_day", "monday"),
    [
        (None, date(2026, 10, 5)),  # 기본은 다음 주(오늘이 일요일이면 바로 내일부터)
        (date(2026, 10, 5), date(2026, 10, 5)),
        (date(2026, 10, 11), date(2026, 10, 5)),  # 일요일은 그 주의 끝
        (date(2026, 10, 12), date(2026, 10, 12)),
    ],
)
def test_week_runs_monday_to_sunday(requested_day: date | None, monday: date) -> None:
    assert week_start(FIXED_NOW, requested_day) == monday


def test_sunday_work_stays_in_its_week_and_monday_starts_the_next(
    client: TestClient, item: WorkItem
) -> None:
    add_work(client, item.site_id, "2026-10-11", "06:00", "07:00")
    add_work(client, item.site_id, "2026-10-12", "18:00", "19:00")

    this_week = sheet(client, item.site_id)
    next_week = sheet(client, item.site_id, "2026-10-12")

    assert "10월 5일(월) ~ 10월 11일(일)" in this_week
    assert "06:00–07:00" in this_week and "18:00–19:00" not in this_week
    assert "18:00–19:00" in next_week and "06:00–07:00" not in next_week
    # 잘못된 날짜는 기본(다음 주)을 보인다
    assert "10월 5일(월) ~ 10월 11일(일)" in sheet(client, item.site_id, "2026-13-40")


def test_checks_use_the_same_rules_as_the_home_check(
    client: TestClient, session: Session, item: WorkItem
) -> None:
    item.performing_participant_id = None  # 업체 필수(D-076) 전에 등록한 작업
    session.commit()
    add_work(client, item.site_id, "2026-10-07", "08:00", "10:00", location="101동 3층")
    add_work(client, item.site_id, "2026-10-07", "09:00", "11:00", location="101동 3층")
    add_work(client, item.site_id, "2026-10-08", "08:00", "10:00", location="101동 3층")
    add_work(client, item.site_id, "2026-10-08", "10:00", "11:00", location="101동 3층")  # 맞닿음

    page = sheet(client, item.site_id)

    assert "실행 업체 미지정" in page and "위치 없음" in page
    assert page.count("같은 곳 같은 시간") == 2  # 10/7 두 건만, 10:00에 끝나고 시작하면 겹침 아님
    assert "점검</dt><dd>3건" in page  # 미지정·위치 없음인 내일 작업 + 10/7 겹친 두 건


def test_open_actions_and_last_weeks_confirmed_change_are_listed(
    client: TestClient, session: Session, item: WorkItem, team: dict[str, Any], requested: int
) -> None:
    page = sheet(client, item.site_id)
    assert "펌프카 예약 변경" in page and "요청 대기" in page
    assert "가상골조" in page  # 조치를 맡은 업체
    assert "→ 10/06(화) 10:00-13:00" in page  # 10/4 확정, 그 주 시작 전 7일 안
    # 다음 주 표의 확정 변경 기간(10/5~10/11)에는 10/4 확정이 들어가지 않는다
    assert "→ 10/06(화)" not in sheet(client, item.site_id, "2026-10-12")

    assert do(team["framer"], item, requested, action(session), "accept").status_code == 303
    report = do(team["framer"], item, requested, action(session), "report",
                body="예약 변경", performed_date="2026-10-04", performed_time="14:30")  # fmt: skip
    assert report.status_code == 303
    assert "확인 대기" in sheet(client, item.site_id)  # 검증 전까지는 안 끝난 조치
    assert do(team["safety"], item, requested, action(session), "verify").status_code == 303
    assert "펌프카 예약 변경" not in sheet(client, item.site_id)


def test_viewer_sees_no_contacts_and_outsider_gets_404(
    client: TestClient, browser: Browser, item: WorkItem
) -> None:
    viewer = join(client, browser, item.site_id, VIEWER, "viewer")
    page = sheet(viewer, item.site_id)
    assert "철골 작업" in page and "tel:" not in page
    assert browser(OUTSIDER).get(f"/reports/{item.site_id}/weekly").status_code == 404
