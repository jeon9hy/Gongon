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
