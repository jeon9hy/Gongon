"""주간 보기(S08-3, D-041): 예보가 있는 날만 판정하고, 자료가 성긴 날은 신뢰도를 낮춰 표시한다."""

from datetime import date
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.features.judgments.models import Judgment
from tests.fakes import FakeKma

SITE: dict[str, Any] = {
    "name": "○○현장",
    "address": "서울 중구 세종대로 110",
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
    location = client.post("/sites", data={**SITE, **changes}, follow_redirects=False).headers[
        "location"
    ]
    return int(location.split("site_id=")[1].split("&")[0])


def week_html(page: str) -> str:
    """주간 표의 열 머리(날짜·신뢰도)와 칸. 표 아래 설명 문구는 뺀다."""
    start = page.index('id="week-title"')
    return page[start : page.index("</table>", start)]


def test_week_judges_covered_days_and_marks_sparse_days(
    client: TestClient, session: Session, fake_kma: FakeKma
) -> None:
    # 고정 시각 10/4 → 내일 10/5. 10/6은 1시간 간격, 10/7은 3시간 간격(실제 4일 뒤 응답 형태),
    # 10/8은 작업 시간(07~17시) 밖의 00시 값뿐이라 판정하지 않는다.
    for hour in range(24):
        fake_kma.set_hour("20261006", hour, **CALM)
    for hour in range(0, 24, 3):
        fake_kma.set_hour("20261007", hour, **CALM)
    fake_kma.set_hour("20261006", 10, WSD="12.0")  # 철골 풍속 기준(10 m/s 이상)에 해당
    fake_kma.set_hour("20261008", 0, **CALM)  # 실제 응답처럼 마지막 날은 00시 값 하나뿐
    site_id = add_site(client)

    client.post("/judgments/run", data={"site_id": site_id})

    days = sorted({d for d in session.scalars(select(Judgment.target_date))})
    assert days == [date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7)]
    assert len(fake_kma.calls) == 1  # 예보는 한 번만 받아 여러 날에 쓴다
    steel = {
        j.target_date: j.verdict
        for j in session.scalars(select(Judgment).where(Judgment.work_type == "철골 작업"))
    }
    assert steel[date(2026, 10, 6)] == "중지 검토"
    # 3시간 간격인 날은 값이 없는 시각을 정상으로 채우지 않는다
    assert steel[date(2026, 10, 7)] == "판정 불가"

    week = week_html(client.get("/dashboard", params={"site_id": site_id}).text)
    assert week.count("신뢰도 높음") == 2  # 10/5, 10/6
    assert week.count("신뢰도 보통") == 1  # 10/7
    assert week.count("예보 없음") == 4  # 10/8~10/11
    assert "예보 대기" in week


def test_week_marks_days_outside_work_period(client: TestClient, fake_kma: FakeKma) -> None:
    site_id = add_site(client, work_end_date="2026-10-06")  # 10/7부터 작업 기간 밖

    client.post("/judgments/run", data={"site_id": site_id})

    week = week_html(client.get("/dashboard", params={"site_id": site_id}).text)
    assert week.count("기간 밖") == 5  # 10/7~10/11


def test_detail_card_defaults_to_highest_verdict_and_can_switch(
    client: TestClient, fake_kma: FakeKma
) -> None:
    fake_kma.set_hour(
        "20261005", 10, WSD="12.0"
    )  # 철골만 풍속 기준에 해당(콘크리트는 풍속 기준 없음)
    site_id = add_site(client, work_types=["콘크리트 타설", "철골 작업"])
    client.post("/judgments/run", data={"site_id": site_id})

    page = client.get("/dashboard", params={"site_id": site_id}).text
    switched = client.get("/dashboard", params={"site_id": site_id, "work": "콘크리트 타설"}).text

    # 목록 순서상 콘크리트가 먼저지만 가장 높은 단계(중지 검토)인 철골을 먼저 보여 준다
    assert '<h2 class="h2">철골 작업 판정</h2>' in page
    assert '<h2 class="h2">콘크리트 타설 판정</h2>' in switched
    assert "work=%EC%BD%98" in switched  # 그래프 요소·시각을 바꿔도 고른 작업을 유지


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

    client.post("/judgments/run", data={"site_id": site_id})
    client.post("/judgments/run", data={"site_id": site_id})

    assert len(fake_kma.mid_calls) == 1  # 같은 발표·구역은 다시 받지 않는다
    assert fake_kma.mid_calls[0]["regId"] == "11B00000"  # 서울 → 서울·인천·경기
    # 중기예보 참고는 판정 내역에 저장하지 않는다
    assert {d.isoformat() for d in session.scalars(select(Judgment.target_date))} == {"2026-10-05"}
    week = week_html(client.get("/dashboard", params={"site_id": site_id}).text)
    assert week.count("신뢰도 낮음") == 2  # 10/8, 10/9
    assert (
        week.count("예보 없음") == 4
    )  # 10/6·10/7(단기·중기 모두 없음), 10/10·10/11(가짜에 값 없음)
    assert "오후 흐리고 비 60%" in week  # 철골(강우 기준) → 확인 필요 사유
    assert "wv--ref" in week
    assert "중지 검토" not in week.split("10/08")[1]  # 중기예보로는 확인 필요보다 높이지 않는다
