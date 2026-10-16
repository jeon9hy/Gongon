"""홈의 오늘 작업(C04-5): 오늘 작업만, 시작 시각 순, 지금 시각 기준 예정·진행 중·끝남.

conftest.FIXED_NOW = 2026-10-04 15:00(KST). 시작이 지금과 같으면 진행 중, 끝이 지금과 같으면 끝남.
"""

import re
from datetime import date, time
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.features.schedules.models import WorkItem

SITE: dict[str, Any] = {
    "name": "가상A현장",
    "road_address": "서울 중구 세종대로 110",
    "latitude": "37.5665",
    "longitude": "126.9780",
    "work_start_date": "2026-10-01",
    "work_end_date": "2026-12-31",
}


def add_work(client: TestClient, site_id: int, day: str, start: str, end: str, work: str) -> None:
    response = client.post(
        "/schedule",
        data={"site_id": site_id, "work_types": work, "work_date": day, "work_dates": day,
              "start": start, "end": end},
        follow_redirects=False,
    )  # fmt: skip
    assert response.status_code == 303, response.text


def rows(page: str) -> list[tuple[str, str]]:
    """오늘 작업 카드의 (단계, 시간) 목록(화면 순서)."""
    return re.findall(
        r'todaycard--(\w+)".*?<span class="todaycard__time">([^<]+)</span>', page, re.S
    )


def add_past(session: Session, site_id: int, start: time, end: time, work: str) -> None:
    """이미 시작했거나 끝난 오늘 작업. 지금보다 이른 시작은 화면으로 못 올려 직접 넣는다(D-064)."""
    item = WorkItem(site_id=site_id, work_type=work, work_date=date(2026, 10, 4),
                    start_local=start, end_local=end, location="", memo="")  # fmt: skip
    session.add(item)
    session.commit()


def test_home_lists_only_today_in_start_order_with_phase_at_boundaries(
    client: TestClient, session: Session
) -> None:
    location = client.post("/sites", data=SITE, follow_redirects=False).headers["location"]
    site_id = int(location.split("site_id=")[1].split("&")[0])
    add_work(client, site_id, "2026-10-04", "15:05", "16:00", "고소작업대")  # 아직 시작 전
    add_past(session, site_id, time(14, 0), time(15, 0), "철골 작업")  # 끝 = 지금 → 끝남
    add_past(session, site_id, time(15, 0), time(17, 0), "콘크리트 타설")  # 시작 = 지금
    add_work(client, site_id, "2026-10-05", "09:00", "12:00", "철골 작업")  # 내일은 빠진다

    page = client.get("/").text

    assert rows(page) == [
        ("done", "14:00–15:00"), ("now", "15:00–17:00"), ("before", "15:05–16:00")
    ]  # fmt: skip
    assert "오늘 작업 3건" in page
    for label in ("진행 중", "예정", "끝남"):
        assert f"<dt>{label}</dt><dd>1</dd>" in page
    assert '<span class="sechead__date">10월 5일(월)</span>' in page  # 내일 준비는 아래에


def test_home_without_today_work_says_so(client: TestClient) -> None:
    client.post("/sites", data=SITE, follow_redirects=False)

    page = client.get("/").text

    assert "오늘은 쉬어 가는 날" in page and "todaycard" not in page
