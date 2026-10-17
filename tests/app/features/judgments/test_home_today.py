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
from tests.fakes import FakeKma

SITE: dict[str, Any] = {
    "name": "가상A현장",
    "road_address": "서울 중구 세종대로 110",
    "latitude": "37.5665",
    "longitude": "126.9780",
    "work_start_date": "2026-10-01",
    "work_end_date": "2026-12-31",
}
TODAY, TOMORROW = date(2026, 10, 4), date(2026, 10, 5)


def make_site(client: TestClient, name: str | None = None) -> int:
    data = SITE if name is None else {**SITE, "name": name}
    location = client.post("/sites", data=data, follow_redirects=False).headers["location"]
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
    pattern = r'class="job job--today job--(\w+)".*?<span class="job__time">([^<]+)</span>'
    return re.findall(pattern, section, re.S)


def test_today_board_lists_today_in_start_order_with_phase_at_boundaries(
    client: TestClient, session: Session
) -> None:
    site_id = make_site(client)
    put(session, site_id, TODAY, time(15, 5), time(16, 0), "고소작업대")  # 아직 시작 전
    put(session, site_id, TODAY, time(14, 0), time(15, 0), "철골 작업")  # 끝 = 지금 → 끝남
    put(session, site_id, TODAY, time(15, 0), time(17, 0), "콘크리트 타설")  # 시작 = 지금

    page = client.get("/").text

    # 끝난 작업(끝 = 지금 포함)은 목록에서 빠진다(개발자 요청 2026-10-17)
    today = board(page, "today")
    assert rows(today) == [
        ("now", "15:00–17:00"), ("before", "15:05–16:00"), ("done", "14:00–15:00")
    ]  # fmt: skip
    # 끝난 작업은 같은 목록 안에 숨겨 두고 '끝난 작업 1건 보기'로 연다
    assert today.count('<li class="is-extra">') == 1 and "끝난 작업 1건 보기" in today
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
    prio = today.split('class="todo"')[1].split("</div>")[0]

    # 먼저 챙길 것: 걸린 작업마다 항목과 작업을 보인다
    assert 'title="이동식 크레인와 같은 곳·같은 시간"' in prio  # 철골 작업 줄
    assert 'title="철골 작업와 같은 곳·같은 시간"' in prio  # 이동식 크레인 줄
    assert "고소작업대와 같은 곳" not in today and "도장·방수와 같은 곳" not in today  # 끝=시작
    assert ">업체 미지정 · 16:00 콘크리트 타설</a>" in prio
    assert "위치 없음" not in prio  # 위치는 선택 입력이라 점검하지 않는다(D-077)
    assert today.count('class="job__warn"') == 3  # 철골·크레인·콘크리트 타설
    assert ">날씨 ·" not in prio  # 오늘은 날씨를 보지 않는다


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

    # 작업 줄: 판정 칸은 그 작업의 판정(판정 전), 다른 확인할 것(변경 검토 중)은 ! 표시
    assert '<span class="badge badge--unknown">판정 전</span>' in tomorrow
    assert 'title="변경 검토 중"' in tomorrow
    assert "일정 ›" not in tomorrow


def test_week_index_shows_seven_days_from_tomorrow(client: TestClient, session: Session) -> None:
    site_id = make_site(client)
    put(session, site_id, TOMORROW, time(9, 0), time(10, 0), "철골 작업")

    page = client.get("/").text
    week = page.split('class="idxweek"')[1].split("</ol>")[0]

    # 7일 원은 버튼이고, 누르면 그날 패널(공종별 요약)이 보인다(슬라이드)
    assert week.count('role="tab"') == 7 and page.count('class="weekslides__panel"') == 7
    assert '<span class="idxday__label">내일</span>' in week  # 첫 칸은 내일
    tomorrow = week.split("</li>")[0]
    assert 'class="ring ring--empty"' in tomorrow  # 판정하기 전에는 점수를 지어내지 않는다
    assert re.search(r'idxday__sub">[^<]+<', tomorrow)  # 점수가 없는 이유를 보인다


def test_week_index_scores_mid_forecast_days_as_reference(
    client: TestClient, session: Session, fake_kma: FakeKma
) -> None:
    # 10/8은 단기예보 밖, 중기예보만 있다(D-069). 철골은 비 기준 → 30% → 85 - 먼 예보 10 = 75.
    fake_kma.mid_item = {"regId": "11B00000", "rnSt4Am": 10, "rnSt4Pm": 30,
                         "wf4Am": "맑음", "wf4Pm": "구름많음"}  # fmt: skip
    site_id = make_site(client)
    put(session, site_id, TOMORROW, time(9, 0), time(10, 0), "철골 작업")
    put(session, site_id, date(2026, 10, 8), time(9, 0), time(10, 0), "철골 작업")
    client.post("/judgments/run", data={"site_id": site_id})

    week = client.get("/").text.split('class="idxweek"')[1].split("</ol>")[0]
    mid_day = week.split("</li>")[3]  # 내일(10/5)부터 네 번째 칸

    assert 'aria-label="공온지수 75(먼 날 예보로 계산)"' in mid_day
    assert "ring--ref" in mid_day and "중기 참고" not in mid_day  # 글 대신 점선 원(D-078)


def test_home_without_any_work_says_so(client: TestClient) -> None:
    make_site(client)

    page = client.get("/").text

    assert "오늘은 쉬어 가는 날" in page and 'class="job job--today' not in page


def test_home_switches_between_sites(client: TestClient, session: Session) -> None:
    first = make_site(client)
    second = make_site(client, "둘째현장")
    put(session, first, TODAY, time(16, 0), time(17, 0), "철골 작업")
    put(session, second, TODAY, time(16, 0), time(17, 0), "도장·방수")

    all_page = client.get("/").text
    only_second = client.get(f"/?site_id={second}").text

    assert 'aria-label="현장 고르기"' in all_page and "오늘 2</span>" in all_page
    today_all = board(all_page, "today")
    assert "철골 작업" in today_all and "도장·방수" in today_all
    today_second = board(only_second, "today")
    assert "도장·방수" in today_second and "철골 작업" not in today_second
    # 내 현장이 아닌 ID는 무시하고 전체를 보인다
    assert "철골 작업" in board(client.get("/?site_id=99999").text, "today")
