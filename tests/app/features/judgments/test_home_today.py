"""홈의 오늘·내일 공온 점검판(C04-5·C04-8, D-062·D-065).

conftest.FIXED_NOW = 2026-10-04 15:00(KST), 내일 = 10-05.
시작이 지금과 같으면 진행 중, 끝이 지금과 같으면 끝남.
점검 항목: 날씨(내일만)·실행 업체·작업 위치·같은 곳 같은 시간 겹침·변경 검토 중.
"""

import re
from datetime import date, time
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.features.schedules.models import WorkItem
from app.features.teams.models import ProjectParticipant

SITE: dict[str, Any] = {
    "name": "가상A현장",
    "road_address": "서울 중구 세종대로 110",
    "latitude": "37.5665",
    "longitude": "126.9780",
    "work_start_date": "2026-10-01",
    "work_end_date": "2026-12-31",
}
TODAY, TOMORROW = date(2026, 10, 4), date(2026, 10, 5)


def make_site(client: TestClient) -> int:
    location = client.post("/sites", data=SITE, follow_redirects=False).headers["location"]
    return int(location.split("site_id=")[1].split("&")[0])


def put(session: Session, site_id: int, day: date, start: time, end: time, work: str,
        location: str = "A구역", performer: int | None = None) -> int:  # fmt: skip
    """작업을 직접 넣는다(지난 시각의 오늘 작업은 화면으로 못 올린다, D-064)."""
    item = WorkItem(site_id=site_id, work_type=work, work_date=day, start_local=start,
                    end_local=end, location=location, memo="",
                    performing_participant_id=performer)  # fmt: skip
    session.add(item)
    session.commit()
    return item.id


def prime_of(session: Session, site_id: int) -> int:
    return session.scalars(
        select(ProjectParticipant.id).where(ProjectParticipant.site_id == site_id)
    ).one()


def board(page: str, key: str) -> str:
    """홈의 오늘·내일 영역(D-065: 오늘=일정·우선순위, 내일=브리핑)."""
    return page.split(f'class="hsec hsec--{key} reveal"')[1].split("</section>")[0]


def rows(section: str) -> list[tuple[str, str]]:
    """오늘 일정의 (단계, 시간) 목록(화면 순서)."""
    pattern = r'class="tline__row tline__row--(\w+)".*?<span class="tline__time">([^<]+)</span>'
    return re.findall(pattern, section, re.S)


def test_today_board_lists_today_in_start_order_with_phase_at_boundaries(
    client: TestClient, session: Session
) -> None:
    site_id = make_site(client)
    put(session, site_id, TODAY, time(15, 5), time(16, 0), "고소작업대")  # 아직 시작 전
    put(session, site_id, TODAY, time(14, 0), time(15, 0), "철골 작업")  # 끝 = 지금 → 끝남
    put(session, site_id, TODAY, time(15, 0), time(17, 0), "콘크리트 타설")  # 시작 = 지금

    page = client.get("/").text

    assert rows(board(page, "today")) == [
        ("done", "14:00–15:00"), ("now", "15:00–17:00"), ("before", "15:05–16:00")
    ]  # fmt: skip
    assert "오늘 작업 3건" in page


def test_checks_flag_missing_company_place_and_true_overlaps_only(
    client: TestClient, session: Session
) -> None:
    site_id = make_site(client)
    prime = prime_of(session, site_id)
    put(session, site_id, TODAY, time(16, 0), time(18, 0), "철골 작업", "B동", prime)
    put(session, site_id, TODAY, time(17, 0), time(19, 0), "이동식 크레인", "B동", prime)  # 겹침
    put(session, site_id, TODAY, time(18, 0), time(20, 0), "고소작업대", "C동", prime)
    put(session, site_id, TODAY, time(20, 0), time(21, 0), "도장·방수", "C동", prime)  # 끝=시작
    put(session, site_id, TODAY, time(16, 0), time(17, 0), "콘크리트 타설", "", None)

    today = board(client.get("/").text, "today")
    prio = today.split('class="prio"')[1]

    # 먼저 챙길 것: 걸린 작업마다 항목과 작업을 보인다
    assert 'title="이동식 크레인와 같은 곳·같은 시간"' in prio  # 철골 작업 줄
    assert 'title="철골 작업와 같은 곳·같은 시간"' in prio  # 이동식 크레인 줄
    assert "고소작업대와 같은 곳" not in today and "도장·방수와 같은 곳" not in today  # 끝=시작
    assert ">업체 미지정</span><a" in prio and ">위치 없음</span><a" in prio
    assert today.count('class="tline__warn"') == 3  # 철골·크레인·콘크리트 타설
    assert ">날씨</span>" not in prio  # 오늘은 날씨를 보지 않는다


def test_tomorrow_board_counts_weather_before_judgment_and_open_change(
    client: TestClient, session: Session
) -> None:
    site_id = make_site(client)
    item_id = put(session, site_id, TOMORROW, time(9, 0), time(12, 0), "철골 작업", "A구역",
                  prime_of(session, site_id))  # fmt: skip
    response = client.post(
        "/changes",
        data={"site_id": site_id, "work_item_id": item_id, "title": "철골 연기",
              "after_work_date": "2026-10-06", "after_start": "10:00", "after_end": "13:00",
              "after_location": "A구역", "reasons": ["material"], "plan_version": 1,
              "submit": "review"},
        follow_redirects=False,
    )  # fmt: skip
    assert response.status_code == 303

    tomorrow = board(client.get("/").text, "tomorrow")

    assert '<span class="crit">날씨 <strong>1</strong></span>' in tomorrow  # 판정 전
    assert '<span class="crit">변경 검토 중 <strong>1</strong></span>' in tomorrow
    assert ">0/1</strong>" in tomorrow
    assert "아직 판정 전이에요" in tomorrow


def test_week_index_shows_seven_days_from_tomorrow(client: TestClient, session: Session) -> None:
    site_id = make_site(client)
    put(session, site_id, TOMORROW, time(9, 0), time(10, 0), "철골 작업")

    page = client.get("/").text
    week = page.split('class="idxweek"')[1].split("</ol>")[0]

    assert week.count('<a href="/dashboard?site_id=') == 7
    assert '<span class="idxday__label">내일</span>' in week  # 첫 칸은 내일
    tomorrow = week.split("</li>")[0]
    assert 'class="ring ring--empty"' in tomorrow  # 판정하기 전에는 점수를 지어내지 않는다
    assert re.search(r'idxday__sub">[^<]+<', tomorrow)  # 점수가 없는 이유를 보인다


def test_home_without_any_work_says_so(client: TestClient) -> None:
    make_site(client)

    page = client.get("/").text

    assert "오늘은 쉬어 가는 날" in page and 'class="tline__row' not in page
