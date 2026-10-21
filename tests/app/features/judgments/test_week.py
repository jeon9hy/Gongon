"""주간 보기(S08-3, D-041·D-050): 예보가 있는 날만 판정하고, 날마다 공온지수를 표시한다."""

import re
from datetime import date
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.features.judgments import service
from app.features.judgments.models import Judgment
from app.features.schedules.models import WorkItem
from tests.conftest import FIXED_NOW
from tests.fakes import FakeKma
from tests.helpers import add_site_with_work

SITE: dict[str, Any] = {
    "name": "○○현장",
    "road_address": "서울 중구 세종대로 110",
    "latitude": "37.5665",
    "longitude": "126.9780",
    "work_start": "07:00",
    "work_end": "17:00",
    "work_start_date": "2026-10-01",
    "work_end_date": "2026-12-31",
    "work_types": ["철골 작업"],
}
CALM = {"PCP": "강수없음", "WSD": "2.0", "SNO": "적설없음", "TMP": "20", "REH": "50"}


def add_site(client: TestClient, **changes: Any) -> int:
    """현장 + 그 공종·시간의 내일 작업(D-059 이전의 현장 기본 판정 상황)."""
    return add_site_with_work(client, {**SITE, **changes})


def add_item(client: TestClient, site_id: int, day: str, work_type: str = "철골 작업") -> None:
    data = {
        "site_id": str(site_id),
        "work_types": work_type,
        "work_date": day,
        "start": "07:00",
        "end": "17:00",
        "location": "",
        "memo": "",
    }
    assert client.post("/schedule", data=data, follow_redirects=False).status_code == 303


def day_scores(week: str) -> dict[str, int]:
    """열 머리마다 공온지수 점수(날짜 'MM/DD' → 점수). 점수가 없는 날은 빠진다."""
    found = re.findall(r'(\d\d/\d\d)\(.\)</span>\s*<span class="gidx[^"]*"[^>]*><b>(\d+)</b>', week)
    return {day: int(score) for day, score in found}


def week_html(page: str) -> str:
    """주간 표의 열 머리(날짜·공온지수)와 칸. 표 아래 설명 문구는 뺀다."""
    start = page.index('id="week-title"')
    return page[start : page.index("</table>", start)]


def test_week_judges_covered_days_and_marks_sparse_days(
    client: TestClient, session: Session, fake_kma: FakeKma
) -> None:
    # 고정 시각 10/4 → 내일 10/5. 10/6은 1시간 간격, 10/7은 3시간 간격(실제 4일 뒤 응답 형태),
    # 10/8은 00시 값뿐이지만 같은 날 값으로 작업 시간 전체를 추정해 판정한다(D-053).
    for hour in range(24):
        fake_kma.set_hour("20261006", hour, **CALM)
    for hour in range(0, 24, 3):
        fake_kma.set_hour("20261007", hour, **CALM)
    fake_kma.set_hour("20261006", 10, WSD="12.0")  # 철골 풍속 기준(10 m/s 이상)에 해당
    fake_kma.set_hour("20261008", 0, **CALM)  # 실제 응답처럼 마지막 날은 00시 값 하나뿐
    site_id = add_site(client)
    for day in ("2026-10-06", "2026-10-07", "2026-10-08"):
        add_item(client, site_id, day)  # 모레부터는 등록한 작업만 판정한다

    client.post("/judgments/run", data={"site_id": site_id})

    days = sorted({d for d in session.scalars(select(Judgment.target_date))})
    assert days == [date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7), date(2026, 10, 8)]
    assert len(fake_kma.calls) == 1  # 예보는 한 번만 받아 여러 날에 쓴다
    steel = {
        j.target_date: j.verdict
        for j in session.scalars(select(Judgment).where(Judgment.work_type == "철골 작업"))
    }
    assert steel[date(2026, 10, 6)] == "중지 검토"
    # 3시간 간격인 날은 같은 날 가까운 시각 값으로 추정한다(기준을 넘으면 확인 필요까지)
    assert steel[date(2026, 10, 7)] == "진행"
    assert steel[date(2026, 10, 8)] == "진행"

    week = week_html(client.get("/dashboard", params={"site_id": site_id}).text)
    scores = day_scores(week)
    assert set(scores) == {"10/05", "10/06", "10/07", "10/08"}  # 판정을 저장한 날만 공온지수
    assert scores["10/06"] <= 30  # 중지 검토가 있는 날은 30점까지(D-050)
    assert week.count(">작업 없음<") == 3  # 10/9~10/11: 등록한 작업이 없어 판정·표시하지 않음


def test_week_marks_days_outside_work_period(client: TestClient, fake_kma: FakeKma) -> None:
    site_id = add_site(client, work_end_date="2026-10-06")  # 10/7부터 작업 기간 밖

    client.post("/judgments/run", data={"site_id": site_id})

    week = week_html(client.get("/dashboard", params={"site_id": site_id}).text)
    assert week.count("기간 밖") == 5  # 10/7~10/11


def test_detail_card_defaults_to_highest_verdict_and_can_switch(
    client: TestClient, fake_kma: FakeKma, session: Session
) -> None:
    # 철골만 풍속 기준에 해당(콘크리트는 풍속 기준 없음)
    fake_kma.set_hour("20261005", 10, WSD="12.0")
    site_id = add_site(client, work_types=["콘크리트 타설", "철골 작업"])
    client.post("/judgments/run", data={"site_id": site_id})

    page = client.get("/dashboard", params={"site_id": site_id}).text
    concrete = session.scalars(
        select(WorkItem.id).where(WorkItem.work_type == "콘크리트 타설")
    ).one()
    switched = client.get(
        "/dashboard", params={"site_id": site_id, "work": f"item:{concrete}"}
    ).text

    # 목록 순서상 콘크리트가 먼저지만 가장 높은 단계(중지 검토)인 철골을 먼저 보여 준다
    assert 'id="work-detail-title">철골 작업 판정</h2>' in page
    assert 'id="work-detail-title">콘크리트 타설 판정</h2>' in switched
    # 기본 진입은 모달을 닫아 두고, 작업을 골라 들어오면 연다
    assert 'id="work-detail" autofocus aria-labelledby="work-detail-title" data-open' not in page
    assert 'id="work-detail" autofocus aria-labelledby="work-detail-title" data-open' in switched
    assert f"work=item%3A{concrete}" in switched  # 그래프 요소·시각을 바꿔도 고른 작업을 유지


def test_days_beyond_short_forecast_show_mid_forecast_reference(
    client: TestClient, session: Session, fake_kma: FakeKma
) -> None:
    # 고정 시각 10/4 15:00 → 최근 중기 발표 10/4 06:00, 4일 후 = 10/8. 단기 가짜는 10/5만 있다.
    fake_kma.mid_item = {
        "regId": "11B00000",
        "rnSt4Am": 20, "rnSt4Pm": 30, "wf4Am": "구름많음", "wf4Pm": "구름많음",
        "rnSt5Am": 30, "rnSt5Pm": 60, "wf5Am": "흐림", "wf5Pm": "흐리고 비",
    }  # fmt: skip
    site_id = add_site(client)
    add_item(client, site_id, "2026-10-08")
    add_item(client, site_id, "2026-10-09")

    client.post("/judgments/run", data={"site_id": site_id})
    client.post("/judgments/run", data={"site_id": site_id})

    assert len(fake_kma.mid_calls) == 1  # 같은 발표·구역은 다시 받지 않는다
    assert fake_kma.mid_calls[0]["regId"] == "11B00000"  # 서울 → 서울·인천·경기
    # 중기예보 참고는 판정 내역에 저장하지 않는다
    assert {d.isoformat() for d in session.scalars(select(Judgment.target_date))} == {"2026-10-05"}
    week = week_html(client.get("/dashboard", params={"site_id": site_id}).text)
    assert "중기 참고" not in week  # 사용자에게 떠넘기는 문구 대신 점선 원·풀이로 구분(D-078)
    # 중기 참고 점수(D-069): 철골은 비 기준이 있어 그날 최고 강수확률로 낮추고 먼 예보 10점 감점.
    # 10/8: 30% → 85 - 10 = 75. 10/9: 60% → 70 - 10 = 60(비 예보 '확인 필요' 상한 70보다 낮음).
    scores = day_scores(week)
    assert set(scores) == {"10/05", "10/08", "10/09"}
    assert (scores["10/08"], scores["10/09"]) == (75, 60)
    assert "공온지수 75(먼 날 예보)" in week
    assert week.count(">작업 없음<") == 4  # 10/6·10/7·10/10·10/11: 등록한 작업 없음
    assert "오후 흐리고 비 60%" in week  # 철골(강우 기준) → 확인 필요 사유
    assert "wv--ref" in week
    assert "중지 검토" not in week.split("10/08")[1]  # 중기예보로는 확인 필요보다 높이지 않는다


def test_later_days_without_registered_work_are_not_judged(
    client: TestClient, session: Session, fake_kma: FakeKma
) -> None:
    # 10/6은 예보가 있어도 작업을 등록하지 않았으므로 현장 기본 공종으로 채우지 않는다.
    for hour in range(24):
        fake_kma.set_hour("20261006", hour, **CALM)
    site_id = add_site(client, work_types=["철골 작업", "콘크리트 타설"])

    client.post("/judgments/run", data={"site_id": site_id})

    days = {d.isoformat() for d in session.scalars(select(Judgment.target_date))}
    assert days == {"2026-10-05"}  # 내일만 작업이 없을 때 기본 공종으로 판정(D-023)
    week = week_html(client.get("/dashboard", params={"site_id": site_id}).text)
    assert week.count(">작업 없음<") == 6


def test_rerun_with_same_forecast_says_unchanged_and_when_next(client: TestClient) -> None:
    site_id = add_site(client)
    client.post("/judgments/run", data={"site_id": site_id})

    again = client.post("/judgments/run", data={"site_id": site_id}, follow_redirects=False)
    page = client.get(again.headers["location"]).text

    assert "ran=unchanged" in again.headers["location"]
    # 고정 시각 10/4 15:00 → 최근 발표 14시, 다음 발표 17시(10분 뒤 제공)
    assert "새로 발표된 예보가 없어 판정이 그대로입니다. 다음 예보 17:00 발표(17:10 반영)" in page


def test_rerun_updates_last_checked_time_without_new_judgments(
    client: TestClient, session: Session
) -> None:
    from datetime import datetime, timedelta

    from app.core.clock import now_kst
    from tests.conftest import FIXED_NOW

    site_id = add_site(client)
    client.post("/judgments/run", data={"site_id": site_id})
    first_rows = list(session.scalars(select(Judgment.id)))

    later: datetime = FIXED_NOW + timedelta(minutes=50)  # 15:50, 아직 14시 발표 예보
    client.app.dependency_overrides[now_kst] = lambda: later  # type: ignore[attr-defined]
    client.post("/judgments/run", data={"site_id": site_id})

    assert list(session.scalars(select(Judgment.id))) == first_rows  # 판정 기록은 그대로
    home = client.get("/").text
    dashboard = client.get("/dashboard", params={"site_id": site_id}).text
    assert "15:50 확인" in home  # 사용자에게는 확인 시각이 갱신된다(홈 카드는 짧게)
    assert "10월 4일 15:50 확인 · 14:00 발표 예보" in dashboard


def test_week_groups_take_the_highest_cell_of_each_day_and_expand_to_work_kinds(
    client: TestClient, session: Session, fake_kma: FakeKma
) -> None:
    # C04-31: 7일 표 묶음 줄. 철골만 풍속 기준에 해당 → 같은 묶음의 그날 칸은 중지 검토.
    fake_kma.set_hour("20261005", 10, WSD="12.0")
    site_id = add_site(client, work_types=["콘크리트 타설", "철골 작업"])
    concrete = session.scalars(select(WorkItem).where(WorkItem.work_type == "콘크리트 타설")).one()
    concrete.location = "101동 9층 2구역"
    session.commit()
    client.post("/judgments/run", data={"site_id": site_id})

    view = service.build_dashboard(session, None, site_id, None, None, FIXED_NOW)
    assert view is not None

    (company,) = view.week_groups  # 두 작업 모두 기본 실행 업체
    assert company.count == 2 and company.cells[0].verdict == "중지 검토"
    assert {r.work_type: r.cells[0].verdict for r in company.types} == {
        "콘크리트 타설": "판정 불가",  # 가짜 예보에 강수 값이 없다
        "철골 작업": "중지 검토",
    }
    # 작업이 없는 날은 묶음 칸도 비운다(판정하지 않음)
    assert all(c.state == "off" and c.verdict is None for c in company.cells[1:])
    places = {g.label: g for g in view.week_place_groups}
    assert list(places) == ["101동 9층", "위치 없음"]
    assert places["101동 9층"].cells[0].verdict == "판정 불가"
    assert places["위치 없음"].cells[0].verdict == "중지 검토"

    page = client.get("/dashboard", params={"site_id": site_id}).text
    assert 'data-groupview="company"' in page and 'data-groupview="place"' in page
    assert page.count('class="week__kind"') == 4 and 'aria-expanded="false"' in page  # 접힘
