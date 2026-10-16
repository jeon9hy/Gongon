"""입력이 바뀐 뒤 예전 판정을 현재 결과처럼 보이지 않는다(C04-1, S08-4-4).

저장된 판정의 격자·작업 시각·기준 버전이 지금 현장·작업·기준과 다르면 '재판정 필요'로 표시하고
판정 단계는 내지 않는다(판정 4단계와 별개). 예전 판정 행은 기록으로 남는다.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.features.judgments import service
from app.features.judgments.models import Judgment
from tests.conftest import FIXED_NOW

SITE: dict[str, Any] = {
    "name": "가상현장",
    "road_address": "서울 중구 세종대로 110",
    "latitude": "37.5665",
    "longitude": "126.9780",
    "work_start": "07:00",
    "work_end": "17:00",
    "work_start_date": "2026-10-01",
    "work_end_date": "2026-12-31",
    "work_types": ["철골 작업"],
}
STEEL = "철골 작업"


def judged_site(client: TestClient) -> int:
    response = client.post("/sites", data=SITE, follow_redirects=False)
    site_id = int(response.headers["location"].split("site_id=")[1].split("&")[0])
    client.post("/judgments/run", data={"site_id": site_id})
    return site_id


def steel_card(session: Session, site_id: int) -> Any:
    view = service.build_dashboard(session, None, site_id, None, None, FIXED_NOW)
    assert view is not None
    return next(c for c in view.cards if c.work_type == STEEL)


def judgment_count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(Judgment)) or 0


def test_unchanged_inputs_show_the_saved_verdict(client: TestClient, session: Session) -> None:
    site_id = judged_site(client)

    card = steel_card(session, site_id)

    assert card.verdict is not None and "재판정 필요" not in card.reason
    assert "재판정 필요" not in client.get(f"/dashboard?site_id={site_id}").text


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"work_start": "08:00"}, "작업 시간"),
        ({"work_end": "16:59"}, "작업 시간"),
        ({"latitude": "35.1796", "longitude": "129.0756"}, "현장 위치"),
    ],
)
def test_site_change_after_judgment_needs_rejudgment(
    client: TestClient, session: Session, changes: dict[str, str], expected: str
) -> None:
    site_id = judged_site(client)
    before = judgment_count(session)

    client.post(f"/sites/{site_id}", data={**SITE, **changes})
    card = steel_card(session, site_id)

    assert card.verdict is None  # 예전 단계를 현재 결과로 보이지 않는다
    assert card.reason.startswith("재판정 필요") and expected in card.reason
    assert judgment_count(session) == before  # 예전 판정은 기록으로 남는다
    assert "재판정 필요" in client.get(f"/dashboard?site_id={site_id}").text


def test_rule_version_change_needs_rejudgment(client: TestClient, session: Session) -> None:
    site_id = judged_site(client)
    # 기준표 버전이 올라간 상황: 저장된 판정은 이전 버전으로 낸 것이 된다.
    session.execute(
        update(Judgment).where(Judgment.work_type == STEEL).values(rule_version="이전 버전")
    )
    session.commit()

    card = steel_card(session, site_id)

    assert card.verdict is None and "판정 기준" in card.reason


def test_rejudging_after_change_clears_the_notice(client: TestClient, session: Session) -> None:
    site_id = judged_site(client)
    client.post(f"/sites/{site_id}", data={**SITE, "work_start": "08:00"})

    client.post("/judgments/run", data={"site_id": site_id})
    card = steel_card(session, site_id)

    assert card.verdict is not None and "재판정 필요" not in card.reason
    assert card.time_range.startswith("08:00")


def test_home_and_week_show_the_notice_not_the_old_verdict(
    client: TestClient, session: Session
) -> None:
    site_id = judged_site(client)
    client.post(f"/sites/{site_id}", data={**SITE, "work_start": "08:00"})

    home = service.build_home(session, None, FIXED_NOW)
    summary = next(s for s in home.sites if s.site_id == site_id)
    steel = next(c for c in summary.cards if c.work_type == STEEL)
    view = service.build_dashboard(session, None, site_id, None, None, FIXED_NOW)
    assert view is not None and view.week is not None
    row = next(r for r in view.week.rows if r.work_type == STEEL)

    assert steel.verdict is None and steel.reason.startswith("재판정 필요")
    assert row.cells[0].verdict is None and row.cells[0].note.startswith("재판정 필요")
