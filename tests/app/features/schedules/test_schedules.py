"""작업 일정 입력(S08-1)과 작업별 판정 연결. 기상청은 가짜(FakeKma), 지금은 2026-10-04 15:00 KST."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.features.judgments.models import Judgment
from app.features.schedules.models import WorkItem
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
    "work_types": ["철골 작업", "고소작업대"],
}
ITEM: dict[str, str] = {
    "work_type": "철골 작업",
    "work_date": "2026-10-05",  # 내일(판정 대상)
    "start": "09:00",
    "end": "12:00",
    "location": "A구역",
}
STEEL = Judgment.work_type == "철골 작업"


def add_site(client: TestClient, **changes: Any) -> int:
    location = client.post("/sites", data={**SITE, **changes}, follow_redirects=False).headers[
        "location"
    ]
    return int(location.split("site_id=")[1].split("&")[0])


def add_item(client: TestClient, site_id: int, **changes: str) -> Any:
    data = {**ITEM, **changes, "site_id": str(site_id)}
    return client.post("/schedule", data=data, follow_redirects=False)


def run(client: TestClient, site_id: int) -> None:
    response = client.post("/judgments/run", data={"site_id": site_id}, follow_redirects=False)
    assert response.status_code == 303


def test_item_is_saved_and_listed_under_its_day(client: TestClient) -> None:
    site_id = add_site(client)
    response = add_item(client, site_id)
    assert response.status_code == 303
    page = client.get(response.headers["location"]).text
    assert "작업을 추가했습니다" in page
    assert "09:00–12:00" in page and "A구역" in page


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"work_type": "고소작업대 아님"}, "현장에 등록한 공종"),
        (
            {"work_type": "콘크리트 타설"},
            "현장에 등록한 공종",
        ),  # 공종 목록에는 있지만 이 현장에는 없음
        ({"work_date": "2026-10-04"}, "내일 이후"),  # 오늘
        ({"work_date": "2027-01-01"}, "작업 기간"),  # 현장 기간 밖
        ({"start": "12:00", "end": "12:00"}, "종료는 시작보다"),
        ({"start": "9시"}, "00:00 형식"),
        ({"location": "가" * 61}, "60자 이하"),
    ],
)
def test_invalid_item_is_rejected_and_not_saved(
    client: TestClient, session: Session, changes: dict[str, str], message: str
) -> None:
    site_id = add_site(client)
    response = add_item(client, site_id, **changes)
    assert response.status_code == 422
    assert message in response.text
    assert session.scalars(select(WorkItem)).first() is None


def test_item_of_another_site_cannot_be_deleted(client: TestClient, session: Session) -> None:
    mine = add_site(client)
    other = add_site(client, name="△△현장")
    add_item(client, mine)
    item_id = session.scalars(select(WorkItem.id)).one()

    response = client.post(f"/schedule/{item_id}/delete", data={"site_id": other})

    assert response.status_code == 404
    assert session.scalars(select(WorkItem.id)).one() == item_id


def test_items_are_judged_separately_and_rerun_adds_nothing(
    client: TestClient, session: Session, fake_kma: FakeKma
) -> None:
    fake_kma.set_hour("20261005", 14, WSD="12.0")  # 14시만 강풍
    site_id = add_site(client)
    add_item(client, site_id)  # 09~12 A구역: 강풍 시각 밖
    add_item(client, site_id, start="13:00", end="16:00", location="B구역")  # 강풍 시각 포함

    run(client, site_id)
    run(client, site_id)  # 같은 예보·기준·작업이면 다시 저장하지 않는다

    steel = session.scalars(select(Judgment).where(STEEL).order_by(Judgment.id)).all()
    assert [(j.work_start_at.hour, j.work_end_at.hour, j.verdict) for j in steel] == [
        (9, 12, "진행"),
        (13, 16, "중지 검토"),
    ]
    assert all(j.work_item_id is not None for j in steel)
    # 그날 작업이 있으면 작업에 없는 공종(고소작업대)은 현장 기본 시간으로 따로 판정하지 않는다.
    types = set(session.scalars(select(Judgment.work_type)).all())
    assert types == {"철골 작업", "폭염(공통)"}

    dashboard = client.get(f"/dashboard?site_id={site_id}").text
    assert "철골 작업 · A구역" in dashboard and "철골 작업 · B구역" in dashboard


def test_day_without_items_uses_site_default_hours(client: TestClient, session: Session) -> None:
    site_id = add_site(client)
    add_item(client, site_id, work_date="2026-10-06")  # 모레 작업은 내일 판정과 무관

    run(client, site_id)

    steel = session.scalars(select(Judgment).where(STEEL)).one()
    assert (steel.work_start_at.hour, steel.work_end_at.hour) == (7, 17)
    assert steel.work_item_id is None


def test_deleting_item_keeps_its_saved_judgment(client: TestClient, session: Session) -> None:
    site_id = add_site(client)
    add_item(client, site_id)
    run(client, site_id)
    item_id = session.scalars(select(WorkItem.id)).one()

    response = client.post(f"/schedule/{item_id}/delete", data={"site_id": site_id},
                           follow_redirects=False)  # fmt: skip

    assert response.status_code == 303
    session.expire_all()
    steel = session.scalars(select(Judgment).where(STEEL)).one()
    assert steel.work_item_id is None  # 연결만 끊기고 판정 기록은 남는다


def test_dashboard_opens_when_first_card_has_daily_elements(
    client: TestClient, fake_kma: FakeKma
) -> None:
    # 회귀: 콘크리트(일평균기온 등 하루 단위 요소)가 대표 판정이면 그래프 탭 만들다 500이 났다.
    for hour in range(24):
        fake_kma.set_hour("20261006", hour, TMP="20", REH="50", PCP="강수없음", WSD="2.0")
    site_id = add_site(client, work_types=["콘크리트 타설"])
    run(client, site_id)

    response = client.get(f"/dashboard?site_id={site_id}")

    assert response.status_code == 200
    assert "콘크리트 타설" in response.text
