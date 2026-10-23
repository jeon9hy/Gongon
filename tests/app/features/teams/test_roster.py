"""참여 업체·담당자 명부(C04-9, D-066, collab-contract §2-1).

가상건설(원청)·가상펌프·가상골조 등은 C01 합성 시나리오의 가상 회사다. 실제 회사가 아니다.
업체 등록·종료·재개, 실행 업체 선택, 명부 연락처 노출 범위, 계정 연결, 같은 이름 업체 처리를 본다.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.features.auth import service as auth_service
from app.features.schedules.models import WorkItem
from app.features.teams.models import ParticipantContact, ProjectMembership, ProjectParticipant
from tests.conftest import DEFAULT_USER, Browser

SITE: dict[str, Any] = {
    "name": "가상A현장",
    "road_address": "서울 중구 세종대로 110",
    "latitude": "37.5665",
    "longitude": "126.9780",
    "work_start_date": "2026-10-01",
    "work_end_date": "2026-12-31",
}
ITEM = {"work_types": "철골 작업", "work_date": "2026-10-05", "start": "09:00", "end": "12:00"}
PUMP_USER = {
    "email": "pump@example.com",
    "display_name": "펌프 기사",
    "organization_name": "가상펌프",
    "password": "pump-password-1",
}
CM_USER = {
    "email": "cm@example.com",
    "display_name": "감리원",
    "organization_name": "가상감리",
    "password": "cm-password-123",
}


def add_site(client: TestClient, name: str = "가상A현장") -> int:
    response = client.post("/sites", data={**SITE, "name": name}, follow_redirects=False)
    assert response.status_code == 303, response.text
    return int(response.headers["location"].split("site_id=")[1].split("&")[0])


def register(client: TestClient, site_id: int, name: str, **extra: Any) -> Any:
    data = {"organization_name": name, "category": "equipment",
            "work_trades": "철근ㆍ콘크리트공사업", **extra}  # fmt: skip
    return client.post(f"/sites/{site_id}/participants", data=data, follow_redirects=False)


def participant_named(session: Session, site_id: int, name: str) -> ProjectParticipant:
    session.expire_all()
    names = {
        pid: n
        for pid, n in session.execute(
            text(
                "SELECT p.id, o.name FROM project_participants p"
                " JOIN organizations o ON o.id = p.organization_id WHERE p.site_id = :s"
            ),
            {"s": site_id},
        ).all()
    }
    found = [pid for pid, n in names.items() if n == name]
    assert len(found) == 1, names
    participant = session.get(ProjectParticipant, found[0])
    assert participant is not None
    return participant


def add_contact(client: TestClient, site_id: int, participant_id: int, **data: str) -> Any:
    form = {"contact_name": "오상훈", "job_title": "기사", "phone": "010-0000-0000", **data}
    return client.post(
        f"/sites/{site_id}/participants/{participant_id}/contacts", data=form,
        follow_redirects=False,
    )  # fmt: skip


def add_member(client: TestClient, site_id: int, email: str, role: str, **extra: str) -> Any:
    data = {"email": email, "role": role, **extra}
    return client.post(f"/sites/{site_id}/members", data=data, follow_redirects=False)


@pytest.fixture
def site_id(client: TestClient) -> int:
    return add_site(client)


def test_coordinator_registers_company_without_people(
    client: TestClient, site_id: int, session: Session
) -> None:
    response = register(client, site_id, "가상펌프", trade_note="펌프카", joined_on="2026-10-01")

    assert response.status_code == 303
    pump = participant_named(session, site_id, "가상펌프")
    assert (pump.kind, pump.category, pump.trade_note) == ("subcontractor", "equipment", "펌프카")
    assert auth_service.organizations_with_users(session, [pump.organization_id]) == frozenset()
    page = client.get(f"/sites/{site_id}/members").text
    assert "가상펌프" in page and "장비 임대" in page and "2026-10-01부터" in page


def test_same_name_company_warns_and_saves_only_after_confirm(
    client: TestClient, site_id: int, session: Session
) -> None:
    register(client, site_id, "가상펌프")

    warned = register(client, site_id, "  가상펌프 ")
    confirmed = register(client, site_id, "가상펌프", confirm_same_name="1")

    assert warned.status_code == 422 and "같은 이름의 업체" in warned.text
    assert "따로 등록" in warned.text
    assert confirmed.status_code == 303
    count = session.scalar(text("SELECT count(*) FROM project_participants WHERE site_id = :s"),
                           {"s": site_id})  # fmt: skip
    assert count == 3  # 원청 + 가상펌프 두 곳(자동 병합 없음)


def test_ended_company_leaves_choices_but_keeps_existing_work(
    client: TestClient, site_id: int, session: Session
) -> None:
    register(client, site_id, "가상펌프")
    pump = participant_named(session, site_id, "가상펌프")
    data = {**ITEM, "site_id": site_id, "performing_participant_id": str(pump.id)}
    assert client.post("/schedule", data=data, follow_redirects=False).status_code == 303

    register(client, site_id, "가상크레인")  # 다른 협력업체가 있어야 작업 추가 자체는 열린다(D-076)
    ended = client.post(f"/sites/{site_id}/participants/{pump.id}/end", follow_redirects=False)
    rejected = client.post("/schedule", data={**data, "work_date": "2026-10-06"})
    item = session.scalars(select(WorkItem)).one()
    kept = client.post(
        f"/schedule/{item.id}/edit",
        data={"site_id": site_id, "day": "2026-10-05", "work_date": "2026-10-05",
              "start": "09:00", "end": "13:00", "location": "", "memo": "",
              "performing_participant_id": str(pump.id), "plan_version": 1},
        follow_redirects=False,
    )  # fmt: skip

    assert ended.status_code == 303
    assert rejected.status_code == 422 and "참여 중인 곳" in rejected.text
    assert kept.status_code == 303
    session.expire_all()
    item = session.scalars(select(WorkItem)).one()
    assert (item.performing_participant_id, item.plan_version) == (pump.id, 2)
    page = client.get(f"/schedule?site_id={site_id}&day=2026-10-05").text
    assert "가상펌프 (제외)" in page  # 수정 폼에만, 새 작업 선택지에는 없음
    assert f'<option value="{pump.id}">가상펌프</option>' not in page


def test_resumed_company_can_be_chosen_again(
    client: TestClient, site_id: int, session: Session
) -> None:
    register(client, site_id, "가상펌프")
    pump = participant_named(session, site_id, "가상펌프")
    client.post(f"/sites/{site_id}/participants/{pump.id}/end")

    client.post(f"/sites/{site_id}/participants/{pump.id}/resume")
    data = {**ITEM, "site_id": site_id, "performing_participant_id": str(pump.id)}

    assert client.post("/schedule", data=data, follow_redirects=False).status_code == 303
    assert participant_named(session, site_id, "가상펌프").ended_at is None


def test_prime_cannot_be_ended(client: TestClient, site_id: int, session: Session) -> None:
    prime = participant_named(session, site_id, DEFAULT_USER["organization_name"])

    response = client.post(f"/sites/{site_id}/participants/{prime.id}/end")

    assert response.status_code == 422 and "원청은 제외할 수 없습니다" in response.text
    with pytest.raises(IntegrityError):
        session.execute(text("UPDATE project_participants SET ended_at = now() WHERE id = :i"),
                        {"i": prime.id})  # fmt: skip
    session.rollback()


def test_ids_from_another_site_are_not_found(
    client: TestClient, site_id: int, session: Session
) -> None:
    other = add_site(client, "다른현장")
    register(client, other, "가상펌프")
    foreign = participant_named(session, other, "가상펌프")
    add_contact(client, other, foreign.id)
    contact_id = session.scalars(select(ParticipantContact.id)).one()

    assert client.post(f"/sites/{site_id}/participants/{foreign.id}/end").status_code == 404
    assert add_contact(client, site_id, foreign.id).status_code == 404
    assert client.post(f"/sites/{site_id}/contacts/{contact_id}/remove").status_code == 404
    link = client.post(f"/sites/{site_id}/contacts/{contact_id}/link", data={"email": "x@y.z"})
    assert link.status_code == 404


def test_assignee_cannot_manage_roster(
    browser: Browser, client: TestClient, site_id: int, session: Session
) -> None:
    pump_client = browser(PUMP_USER)
    add_member(client, site_id, PUMP_USER["email"], "assignee")
    pump = participant_named(session, site_id, "가상펌프")

    assert register(pump_client, site_id, "가상레미콘").status_code == 403
    assert pump_client.post(f"/sites/{site_id}/participants/{pump.id}/end").status_code == 403
    assert add_contact(pump_client, site_id, pump.id).status_code == 403


def test_viewer_sees_name_and_title_but_not_phone_or_memo(
    browser: Browser, client: TestClient, site_id: int, session: Session
) -> None:
    register(client, site_id, "가상펌프")
    pump = participant_named(session, site_id, "가상펌프")
    add_contact(client, site_id, pump.id, phone="010-1234-5678", memo="오전만 통화")
    cm_client = browser(CM_USER)
    pump_user = browser(PUMP_USER)
    add_member(client, site_id, CM_USER["email"], "viewer")
    add_member(client, site_id, PUMP_USER["email"], "assignee", same_name=f"attach:{pump.id}")

    viewer_page = cm_client.get(f"/sites/{site_id}/members").text
    assignee_page = pump_user.get(f"/sites/{site_id}/members").text

    assert "오상훈" in viewer_page and "기사" in viewer_page
    assert "010-1234-5678" not in viewer_page and "오전만 통화" not in viewer_page
    assert "010-1234-5678" in assignee_page and "오전만 통화" in assignee_page


def test_member_of_same_named_roster_company_attaches_to_it(
    browser: Browser, client: TestClient, site_id: int, session: Session
) -> None:
    register(client, site_id, "가상펌프")
    pump = participant_named(session, site_id, "가상펌프")
    add_contact(client, site_id, pump.id)
    contact_id = session.scalars(select(ParticipantContact.id)).one()
    browser(PUMP_USER)

    asked = add_member(client, site_id, PUMP_USER["email"], "assignee")
    attached = add_member(client, site_id, PUMP_USER["email"], "assignee",
                          same_name=f"attach:{pump.id}", contact_id=str(contact_id))  # fmt: skip

    assert asked.status_code == 422 and "에 붙이기" in asked.text and "따로 추가" in asked.text
    assert attached.status_code == 303
    user = auth_service.find_user_by_email(session, PUMP_USER["email"])
    assert user is not None
    pump = participant_named(session, site_id, "가상펌프")
    assert pump.organization_id == user.organization_id  # 명부 업체가 가입자의 회사가 됨
    membership = session.scalars(select(ProjectMembership).where(
        ProjectMembership.user_id == user.user_id)).one()  # fmt: skip
    assert membership.participant_id == pump.id
    assert session.get(ParticipantContact, contact_id).user_id == user.user_id  # type: ignore[union-attr]
    assert "펌프 기사 계정 · 담당자" in client.get(f"/sites/{site_id}/members").text


def test_new_colleague_with_same_company_name_can_join_prime_as_coordinator(
    browser: Browser, client: TestClient, site_id: int, session: Session
) -> None:
    colleague = {**PUMP_USER, "email": "works@example.com",
                 "organization_name": DEFAULT_USER["organization_name"]}  # fmt: skip
    browser(colleague)
    prime = participant_named(session, site_id, DEFAULT_USER["organization_name"])

    response = add_member(client, site_id, colleague["email"], "coordinator",
                          same_name=f"attach:{prime.id}")  # fmt: skip

    assert response.status_code == 303
    moved = auth_service.find_user_by_email(session, colleague["email"])
    assert moved is not None and moved.organization_id == prime.organization_id


def test_user_already_on_another_site_is_not_moved_between_companies(
    browser: Browser, client: TestClient, site_id: int, session: Session
) -> None:
    colleague = {**PUMP_USER, "organization_name": DEFAULT_USER["organization_name"]}
    colleague_client = browser(colleague)
    add_site(colleague_client, "동료현장")  # 이미 자기 회사로 다른 현장의 원청
    prime = participant_named(session, site_id, DEFAULT_USER["organization_name"])
    before = auth_service.find_user_by_email(session, colleague["email"])

    response = add_member(client, site_id, colleague["email"], "assignee",
                          same_name=f"attach:{prime.id}")  # fmt: skip

    assert response.status_code == 422 and "옮길 수 없습니다" in response.text
    after = auth_service.find_user_by_email(session, colleague["email"])
    assert before is not None and after is not None
    assert after.organization_id == before.organization_id


def test_contact_links_only_to_user_of_the_same_company(
    browser: Browser, client: TestClient, site_id: int, session: Session
) -> None:
    register(client, site_id, "가상펌프")
    pump = participant_named(session, site_id, "가상펌프")
    add_contact(client, site_id, pump.id)
    add_contact(client, site_id, pump.id, contact_name="두번째")
    first, second = session.scalars(select(ParticipantContact.id).order_by(ParticipantContact.id))
    browser(CM_USER)
    browser(PUMP_USER)
    add_member(client, site_id, PUMP_USER["email"], "assignee", same_name=f"attach:{pump.id}")

    other_company = client.post(f"/sites/{site_id}/contacts/{first}/link",
                                data={"email": CM_USER["email"]})  # fmt: skip
    linked = client.post(f"/sites/{site_id}/contacts/{first}/link",
                         data={"email": PUMP_USER["email"]}, follow_redirects=False)  # fmt: skip
    twice = client.post(f"/sites/{site_id}/contacts/{second}/link",
                        data={"email": PUMP_USER["email"]})  # fmt: skip

    assert other_company.status_code == 422 and "이 업체 소속" in other_company.text
    assert linked.status_code == 303
    assert twice.status_code == 422 and "이미 연결" in twice.text


def test_removed_contact_is_hidden_and_frees_the_account(
    browser: Browser, client: TestClient, site_id: int, session: Session
) -> None:
    register(client, site_id, "가상펌프")
    pump = participant_named(session, site_id, "가상펌프")
    add_contact(client, site_id, pump.id, contact_name="빠질사람")
    contact_id = session.scalars(select(ParticipantContact.id)).one()

    client.post(f"/sites/{site_id}/contacts/{contact_id}/remove")

    session.expire_all()
    assert session.get(ParticipantContact, contact_id).removed_at is not None  # type: ignore[union-attr]
    assert "빠질사람" not in client.get(f"/sites/{site_id}/members").text


def test_contact_input_limits(client: TestClient, site_id: int, session: Session) -> None:
    register(client, site_id, "가상펌프")
    pump = participant_named(session, site_id, "가상펌프")

    empty = add_contact(client, site_id, pump.id, contact_name=" ")
    long_title = add_contact(client, site_id, pump.id, job_title="가" * 41)
    at_limit = add_contact(client, site_id, pump.id, job_title="가" * 40)

    assert empty.status_code == 422 and long_title.status_code == 422
    assert at_limit.status_code == 303


def test_trade_note_fits_one_table_cell(client: TestClient, site_id: int) -> None:
    # 공종 메모는 표 한 칸에 들어가게 20자까지(C04-39 후속). 21자는 저장하지 않는다
    at_limit = register(client, site_id, "가상펌프", trade_note="가" * 20)
    too_long = register(client, site_id, "가상크레인", trade_note="가" * 21)

    assert at_limit.status_code == 303
    assert too_long.status_code == 422 and "공종 메모는 20자 이내" in too_long.text


def test_contact_can_be_edited_by_a_coordinator_only(
    browser: Browser, client: TestClient, site_id: int, session: Session
) -> None:
    register(client, site_id, "가상레미콘")
    pump = participant_named(session, site_id, "가상레미콘")
    add_contact(client, site_id, pump.id)
    session.expire_all()
    contact = session.scalars(
        select(ParticipantContact).where(ParticipantContact.participant_id == pump.id)
    ).one()
    url = f"/sites/{site_id}/contacts/{contact.id}/edit"
    outsider_client = browser(PUMP_USER)
    add_member(client, site_id, PUMP_USER["email"], "assignee")

    edited = client.post(url, data={"contact_name": "오상훈", "job_title": "배차 반장",
                                    "phone": "010-1111-2222"}, follow_redirects=False)  # fmt: skip
    too_long = client.post(url, data={"contact_name": "가" * 41}, follow_redirects=False)
    refused = outsider_client.post(url, data={"contact_name": "바꿈"}, follow_redirects=False)

    assert edited.status_code == 303
    assert too_long.status_code == 422 and refused.status_code == 403
    session.expire_all()
    contact = session.get(ParticipantContact, contact.id)  # type: ignore[assignment]
    assert (contact.name, contact.job_title, contact.phone) == (
        "오상훈",
        "배차 반장",
        "010-1111-2222",
    )
