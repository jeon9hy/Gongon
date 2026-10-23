"""작업 실행 업체·계획 버전·변경 이력·동시 수정(C04-2, collab-contract §3).

가상건설(원청)·가상골조(협력업체)는 C01 합성 시나리오의 가상 회사다.
"""

from datetime import date, time
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.features.judgments import service as judgments_service
from app.features.schedules import service as schedules_service
from app.features.schedules.models import WorkItem, WorkItemRevision
from app.features.schedules.schemas import PlanValues
from app.features.teams.models import ProjectParticipant
from tests.conftest import FIXED_NOW, Browser

SITE: dict[str, Any] = {
    "name": "가상A현장",
    "road_address": "서울 중구 세종대로 110",
    "latitude": "37.5665",
    "longitude": "126.9780",
    "work_start": "07:00",
    "work_end": "17:00",
    "work_start_date": "2026-10-01",
    "work_end_date": "2026-12-31",
    "work_types": ["철골 작업"],
}
ITEM = {
    "work_types": "철골 작업",
    "work_date": "2026-10-05",
    "start": "09:00",
    "end": "12:00",
    "location": "A구역",
}
SUB_USER = {
    "email": "framer@example.com",
    "display_name": "골조 담당",
    "organization_name": "가상골조",
    "password": "framer-password-1",
}


def add_site(client: TestClient, name: str = "가상A현장") -> int:
    response = client.post("/sites", data={**SITE, "name": name}, follow_redirects=False)
    return int(response.headers["location"].split("site_id=")[1].split("&")[0])


def participant_ids(session: Session, site_id: int) -> list[int]:
    return list(
        session.scalars(select(ProjectParticipant.id).where(ProjectParticipant.site_id == site_id))
    )


def add_item(client: TestClient, site_id: int, **changes: str) -> Any:
    return client.post(
        "/schedule", data={**ITEM, **changes, "site_id": site_id}, follow_redirects=False
    )


def only_item(session: Session) -> WorkItem:
    session.expire_all()
    return session.scalars(select(WorkItem)).one()


def edit(client: TestClient, site_id: int, item: WorkItem, **changes: Any) -> Any:
    data = {
        "site_id": site_id,
        "day": item.work_date.isoformat(),
        "work_date": item.work_date.isoformat(),
        "start": f"{item.start_local:%H:%M}",
        "end": f"{item.end_local:%H:%M}",
        "location": item.location,
        "memo": item.memo,
        "performing_participant_id": item.performing_participant_id or "",
        "plan_version": item.plan_version,
        **changes,
    }
    return client.post(f"/schedule/{item.id}/edit", data=data, follow_redirects=False)


@pytest.fixture
def site_id(client: TestClient) -> int:
    return add_site(client)


def add_partner(client: TestClient, site_id: int, name: str = "가상골조") -> None:
    """원청 말고 일할 업체(D-076: 없으면 작업을 올리지 못한다)."""
    response = client.post(
        f"/sites/{site_id}/participants",
        data={
            "organization_name": name,
            "category": "subcontractor",
            "work_trades": "철근ㆍ콘크리트공사업",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text


def test_new_item_can_name_a_performing_company_of_this_site(
    client: TestClient, site_id: int, session: Session
) -> None:
    prime = participant_ids(session, site_id)[0]
    add_partner(client, site_id)

    # 협력업체가 있으면 원청(직영)도 실행 업체로 고를 수 있다
    assert add_item(client, site_id, performing_participant_id=str(prime)).status_code == 303

    item = only_item(session)
    assert (item.performing_participant_id, item.plan_version) == (prime, 1)
    page = client.get(f"/schedule?site_id={site_id}&day=2026-10-05").text
    assert "가상건설 · v1" in page  # 작업 카드
    assert "<dt>실행 업체</dt><dd>가상건설</dd>" in page  # 작업 상세


def test_work_needs_a_partner_company_and_a_performer(
    client: TestClient, site_id: int, session: Session
) -> None:
    # 원청만 있는 현장: 작업을 올리지 못하고 업체 등록을 안내한다(D-076)
    blocked = add_item(client, site_id, performing_participant_id="")
    assert blocked.status_code == 422 and "먼저 참여 업체를 등록해 주세요" in blocked.text
    assert (
        "먼저 참여 업체를 등록해 주세요</strong>" in client.get(f"/schedule?site_id={site_id}").text
    )

    add_partner(client, site_id)
    missing = add_item(client, site_id, performing_participant_id="")

    assert missing.status_code == 422 and "실행 업체를 골라 주세요." in missing.text
    assert session.scalar(select(WorkItem.id)) is None


def test_performer_from_another_site_is_rejected(
    client: TestClient, site_id: int, session: Session
) -> None:
    other = add_site(client, "다른현장")
    foreign = participant_ids(session, other)[0]
    add_partner(client, site_id)

    response = add_item(client, site_id, performing_participant_id=str(foreign))

    assert response.status_code == 422 and "이 현장의 참여 업체" in response.text
    assert session.scalar(select(WorkItem.id)) is None


def test_database_rejects_performer_of_another_site(
    client: TestClient, site_id: int, session: Session
) -> None:
    other = add_site(client, "다른현장")
    add_item(client, site_id)
    item = only_item(session)

    item.performing_participant_id = participant_ids(session, other)[0]
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_edit_saves_previous_plan_and_raises_version(
    client: TestClient, site_id: int, session: Session
) -> None:
    add_item(client, site_id)
    item = only_item(session)
    prime = participant_ids(session, site_id)[0]

    response = edit(client, site_id, item, start="10:00", performing_participant_id=prime)

    assert response.status_code == 303 and "edited=1" in response.headers["location"]
    item = only_item(session)
    assert (item.start_local, item.plan_version, item.performing_participant_id) == (
        time(10, 0), 2, prime
    )  # fmt: skip
    revision = session.scalars(select(WorkItemRevision)).one()
    assert (revision.plan_version, revision.start_local, revision.location) == (
        1, time(9, 0), "A구역"
    )  # fmt: skip
    assert revision.performing_participant_id not in (None, prime)  # 처음엔 기본 협력업체
    assert revision.changed_at == FIXED_NOW and revision.source == "edit"
    page = client.get(response.headers["location"]).text
    assert "v2 · 변경 1번" in page and "v1 10/05 09:00–12:00 · A구역" in page


def test_edit_with_an_outdated_version_is_refused_with_409(
    client: TestClient, site_id: int, session: Session
) -> None:
    add_item(client, site_id)
    opened = only_item(session)
    form_version = opened.plan_version
    assert edit(client, site_id, opened, start="10:00").status_code == 303

    stale = edit(client, site_id, opened, start="11:00", plan_version=form_version)

    assert stale.status_code == 409 and "다른 사람이 먼저" in stale.text
    item = only_item(session)
    assert (item.start_local, item.plan_version) == (time(10, 0), 2)
    assert len(session.scalars(select(WorkItemRevision)).all()) == 1


def test_racing_saves_with_the_same_version_let_only_one_win(
    client: TestClient, site_id: int, session: Session, db_engine: Engine
) -> None:
    add_item(client, site_id)
    # 다른 요청이 같은 버전을 읽어 둔 상태(세션 안의 값은 v1로 남아 있다)
    with Session(db_engine, expire_on_commit=False) as other:
        loaded = other.scalars(select(WorkItem)).one()
        assert edit(client, site_id, only_item(session), start="10:00").status_code == 303

        values = PlanValues(date(2026, 10, 5), time(11, 0), time(12, 0), "A구역", "", None)
        result = schedules_service.apply_plan_change(
            other, loaded, 1, values, changed_by=None, now=FIXED_NOW, source="edit"
        )
        other.rollback()

    assert result == "conflict"
    assert only_item(session).start_local == time(10, 0)


def test_unchanged_edit_keeps_the_version(
    client: TestClient, site_id: int, session: Session
) -> None:
    add_item(client, site_id)

    response = edit(client, site_id, only_item(session))

    assert "unchanged=1" in response.headers["location"]
    assert only_item(session).plan_version == 1
    assert session.scalar(select(WorkItemRevision.id)) is None


@pytest.mark.parametrize(
    "changes",
    [
        {"start": "12:00", "end": "12:00"},  # 시작 = 종료
        {"work_date": "2026-10-03"},  # 어제(오늘은 허용, C04-4)
        {"work_date": "2027-01-01"},  # 현장 작업 기간 밖
        {"plan_version": "abc"},
    ],
)
def test_invalid_edit_changes_nothing(
    client: TestClient, site_id: int, session: Session, changes: dict[str, str]
) -> None:
    add_item(client, site_id)

    response = edit(client, site_id, only_item(session), **changes)

    assert response.status_code in (409, 422)
    assert (only_item(session).plan_version, only_item(session).start_local) == (1, time(9, 0))


def test_only_coordinators_edit_and_deleted_items_cannot_be_edited(
    client: TestClient, browser: Browser, site_id: int, session: Session
) -> None:
    framer = browser(SUB_USER)
    client.post(f"/sites/{site_id}/members", data={"email": SUB_USER["email"], "role": "assignee"})
    add_item(client, site_id)
    item = only_item(session)

    assert edit(framer, site_id, item, start="10:00").status_code == 403
    client.post(f"/schedule/{item.id}/delete", data={"site_id": site_id})
    assert edit(client, site_id, item, start="10:00").status_code == 404
    assert "계획 수정" not in framer.get(f"/schedule?site_id={site_id}&day=2026-10-05").text


def test_editing_time_marks_the_old_judgment_for_rejudgment(
    client: TestClient, site_id: int, session: Session
) -> None:
    add_item(client, site_id)
    client.post("/judgments/run", data={"site_id": site_id})

    edit(client, site_id, only_item(session), start="10:00")
    view = judgments_service.build_dashboard(session, None, site_id, None, None, FIXED_NOW)

    assert view is not None
    card = next(c for c in view.cards if c.work_type.startswith("철골 작업"))
    assert card.verdict is None and "작업 시간" in card.reason
