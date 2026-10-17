"""폭염(공통)은 작업마다 그 작업 시간으로 판정하고 작업 카드에 합친다(C04-3, D-059).

따로 '폭염' 카드·주간 줄을 두지 않는다. 폭염이 더 높은 단계면 카드 단계와 사유('폭염 · …')가 바뀐다.
작업이 없는 날은 판정하지 않는다.
"""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.features.judgments import service
from app.features.judgments.models import Judgment
from engine.kst import KST
from tests.conftest import FIXED_NOW
from tests.fakes import FakeKma

SITE: dict[str, Any] = {
    "name": "가상현장",
    "road_address": "서울 중구 세종대로 110",
    "latitude": "37.5665",
    "longitude": "126.9780",
    "work_start_date": "2026-10-01",
    "work_end_date": "2026-12-31",
}
STEEL = "철골 작업"


def site_with_work(client: TestClient, start: str = "09:00", end: str = "12:00") -> int:
    response = client.post("/sites", data=SITE, follow_redirects=False)
    site_id = int(response.headers["location"].split("site_id=")[1].split("&")[0])
    work = {"site_id": site_id, "work_types": STEEL, "work_dates": "2026-10-05",
            "start": start, "end": end}  # fmt: skip
    assert client.post("/schedule", data=work, follow_redirects=False).status_code == 303
    return site_id


def run(client: TestClient, site_id: int) -> str:
    response = client.post("/judgments/run", data={"site_id": site_id}, follow_redirects=False)
    return str(response.headers["location"])


def test_heat_is_judged_at_the_work_time_and_folded_into_the_work_card(
    client: TestClient, session: Session, fake_kma: FakeKma
) -> None:
    fake_kma.set_hour("20261005", 10, TMP="34", REH="60")  # 작업 시간(09-12) 안의 폭염
    site_id = site_with_work(client)

    run(client, site_id)
    view = service.build_dashboard(session, None, site_id, None, None, FIXED_NOW)

    heat = session.scalars(select(Judgment).where(Judgment.work_type == "폭염(공통)")).one()
    assert heat.work_item_id is not None  # 작업마다, 그 작업 시간(09-12)으로
    assert (heat.work_start_at.astimezone(KST).hour, heat.work_end_at.astimezone(KST).hour) == (
        9,
        12,
    )
    assert view is not None and [c.work_type for c in view.cards] == [STEEL]  # 폭염 카드 없음
    card = view.cards[0]
    assert card.verdict == "확인 필요" and card.reason.startswith("폭염 · ")
    assert card.detail_href == f"/judgments/{heat.id}"  # 단계를 정한 판정의 상세
    assert view.week is not None and [r.work_type for r in view.week.rows] == [STEEL]
    page = client.get(f"/dashboard?site_id={site_id}").text
    assert "폭염(공통)</" not in page


def test_heat_outside_the_work_time_does_not_change_the_card(
    client: TestClient, session: Session, fake_kma: FakeKma
) -> None:
    fake_kma.set_hour("20261005", 14, TMP="34", REH="60")  # 작업(09-12) 밖
    site_id = site_with_work(client)

    run(client, site_id)
    view = service.build_dashboard(session, None, site_id, None, None, FIXED_NOW)

    assert view is not None
    assert view.cards[0].verdict == "진행" and "폭염" not in view.cards[0].reason


def test_work_verdict_higher_than_heat_keeps_the_work_reason(
    client: TestClient, session: Session, fake_kma: FakeKma
) -> None:
    fake_kma.set_hour("20261005", 10, TMP="34", REH="60", WSD="12.0")  # 철골 풍속 중지 검토
    site_id = site_with_work(client)

    run(client, site_id)
    view = service.build_dashboard(session, None, site_id, None, None, FIXED_NOW)

    assert view is not None
    card = view.cards[0]
    assert card.verdict == "중지 검토" and not card.reason.startswith("폭염")


def test_home_summary_uses_the_folded_level_and_lists_registered_work_types(
    client: TestClient, session: Session, fake_kma: FakeKma
) -> None:
    fake_kma.set_hour("20261005", 10, TMP="34", REH="60")
    site_id = site_with_work(client)
    run(client, site_id)

    summary = next(s for s in service.build_home(session, None, FIXED_NOW).sites)

    assert summary.site_id == site_id and summary.verdict == "확인 필요"
    assert summary.work_types == (STEEL,) and summary.work_hours == "09:00–12:00 · 작업 1건"
    assert [c.work_type for c in summary.cards] == [STEEL]


def test_site_without_work_is_not_judged_and_no_forecast_is_fetched(
    client: TestClient, session: Session, fake_kma: FakeKma
) -> None:
    response = client.post("/sites", data=SITE, follow_redirects=False)
    site_id = int(response.headers["location"].split("site_id=")[1].split("&")[0])

    location = run(client, site_id)
    home = client.get("/").text

    assert "ran=no_work" in location
    assert session.scalar(select(Judgment.id)) is None and fake_kma.calls == []
    dashboard = client.get(location).text
    assert "등록한 작업이 없어 판정하지 않았습니다" in dashboard
    assert "‘지금 판정하기’를 누르면" not in dashboard
    assert "내일 일정이 비어 있어요" in home


def test_notice_keeps_check_for_work_without_rules_even_when_heat_is_go(
    client: TestClient, session: Session
) -> None:
    site_id = site_with_work(client)
    response = client.post(
        "/schedule", data={"site_id": site_id, "work_types": "이동식 크레인",
                           "work_dates": "2026-10-05", "start": "09:00", "end": "12:00"}
    )  # fmt: skip
    assert response.status_code == 200
    run(client, site_id)

    view = service.build_dashboard(session, None, site_id, None, None, FIXED_NOW)

    assert view is not None and view.notice is not None
    assert any(i.verdict == "확인 필요" and "이동식 크레인" in i.work for i in view.notice.items)
    notice = client.get(f"/dashboard?site_id={site_id}").text.split('class="message"')[1]
    assert "판정한 공종 모두" not in notice
