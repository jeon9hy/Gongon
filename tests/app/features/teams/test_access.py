"""현장 참여 업체·역할에 따른 접근 범위(C03-2, D-057).

C01 합성 시나리오(가상건설 원청, 가상골조 협력업체, 무관한 회사)로 검증한다. 실제 회사가 아니다.
비참여는 404, 역할 부족은 403, 목록·직접 URL·쓰기 모두 서버에서 막는지 본다.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.features.auth import service as auth_service
from app.features.auth.models import User
from app.features.judgments.models import Judgment, JudgmentRun
from app.features.schedules.models import WorkItem
from app.features.teams import service as teams_service
from app.features.teams.models import ProjectMembership, ProjectParticipant
from tests.conftest import DEFAULT_USER, FIXED_NOW, Browser

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
SUB_USER = {
    "email": "framer@example.com",
    "display_name": "골조 담당",
    "organization_name": "가상골조",
    "password": "framer-password-1",
}
OUTSIDER = {
    "email": "outsider@example.com",
    "display_name": "무관한 사람",
    "organization_name": "무관건설",
    "password": "outsider-password",
}
WORK = {"work_types": "철골 작업", "work_date": "2026-10-06", "start": "08:00", "end": "12:00"}


def add_site(client: TestClient, **changes: Any) -> int:
    response = client.post("/sites", data={**SITE, **changes}, follow_redirects=False)
    assert response.status_code == 303, response.text
    return int(response.headers["location"].split("site_id=")[1].split("&")[0])


def add_member(client: TestClient, site_id: int, email: str, role: str) -> Any:
    return client.post(
        f"/sites/{site_id}/members", data={"email": email, "role": role}, follow_redirects=False
    )


def active_membership(session: Session, email: str, site_id: int) -> ProjectMembership | None:
    user = auth_service.find_user_by_email(session, email)
    assert user is not None
    return session.scalar(
        select(ProjectMembership).where(
            ProjectMembership.user_id == user.user_id,
            ProjectMembership.site_id == site_id,
            ProjectMembership.revoked_at.is_(None),
        )
    )


def colleague_of_default_user(session: Session) -> str:
    """기본 사용자와 같은 회사 동료. 가입 화면은 회사를 새로 만들므로 직접 넣는다."""
    founder = session.scalars(select(User).where(User.email == DEFAULT_USER["email"])).one()
    session.add(
        User(
            email="colleague@example.com",
            display_name="같은 회사 동료",
            password_hash=auth_service.hash_password("colleague-password"),
            organization_id=founder.organization_id,
        )
    )
    session.commit()
    return "colleague@example.com"


@pytest.fixture
def site_id(client: TestClient) -> int:
    return add_site(client)


@pytest.fixture
def judgment_id(client: TestClient, site_id: int, session: Session) -> int:
    tomorrow = {**WORK, "work_date": "2026-10-05"}
    client.post("/schedule", data={"site_id": site_id, **tomorrow})
    client.post("/judgments/run", data={"site_id": site_id})
    found = session.scalar(select(Judgment.id).where(Judgment.site_id == site_id).limit(1))
    assert found is not None
    return found


def test_creating_a_site_makes_founder_company_prime_and_founder_coordinator(
    client: TestClient, site_id: int, session: Session
) -> None:
    participant = session.scalars(select(ProjectParticipant)).one()
    membership = session.scalars(select(ProjectMembership)).one()

    assert (participant.site_id, participant.kind) == (site_id, "prime")
    assert (membership.participant_id, membership.role) == (participant.id, "coordinator")
    assert membership.created_at == FIXED_NOW


@pytest.mark.parametrize(
    "path",
    [
        "/sites?site_id={id}",
        "/schedule?site_id={id}",
        "/dashboard?site_id={id}",
        "/sites/{id}/members",
    ],
)
def test_outsider_cannot_open_site_pages_by_direct_url(
    browser: Browser, site_id: int, path: str
) -> None:
    outsider = browser(OUTSIDER)

    assert outsider.get(path.format(id=site_id)).status_code == 404


def test_outsider_cannot_open_judgment_detail_or_filter_history(
    browser: Browser, judgment_id: int, site_id: int
) -> None:
    outsider = browser(OUTSIDER)

    assert outsider.get(f"/judgments/{judgment_id}").status_code == 404
    history = outsider.get(f"/judgments?site_id={site_id}").text
    assert f"/judgments/{judgment_id}" not in history
    assert SITE["name"] not in history


def test_outsider_lists_show_no_foreign_site(browser: Browser, judgment_id: int) -> None:
    outsider = browser(OUTSIDER)

    for path in ("/home", "/sites", "/dashboard", "/schedule", "/judgments"):
        assert SITE["name"] not in outsider.get(path).text, path


def test_same_company_colleague_without_membership_cannot_see_site(
    browser: Browser, site_id: int, session: Session
) -> None:
    email = colleague_of_default_user(session)
    colleague = browser(None)
    colleague.post("/login", data={"email": email, "password": "colleague-password"})

    assert colleague.get(f"/sites?site_id={site_id}").status_code == 404
    assert SITE["name"] not in colleague.get("/sites").text


def test_outsider_writes_are_refused_and_change_nothing(
    browser: Browser, site_id: int, session: Session
) -> None:
    outsider = browser(OUTSIDER)

    responses = [
        outsider.post(f"/sites/{site_id}", data={**SITE, "name": "탈취"}),
        outsider.post(f"/sites/{site_id}/delete"),
        outsider.post("/schedule", data={"site_id": site_id, **WORK}),
        outsider.post("/judgments/run", data={"site_id": site_id}),
        add_member(outsider, site_id, OUTSIDER["email"], "coordinator"),
    ]

    assert [r.status_code for r in responses] == [404] * 5
    name, deleted_at = session.execute(
        text("SELECT name, deleted_at FROM sites WHERE id = :id"), {"id": site_id}
    ).one()
    assert (name, deleted_at) == (SITE["name"], None)
    assert session.scalar(select(WorkItem.id)) is None
    assert session.scalar(select(JudgmentRun.id)) is None
    assert active_membership(session, OUTSIDER["email"], site_id) is None


def test_subcontractor_assignee_can_view_but_not_change_site(
    client: TestClient, browser: Browser, site_id: int, session: Session
) -> None:
    framer = browser(SUB_USER)
    assert add_member(client, site_id, SUB_USER["email"], "assignee").status_code == 303

    for path in ("/sites?site_id={id}", "/schedule?site_id={id}", "/dashboard?site_id={id}"):
        assert framer.get(path.format(id=site_id)).status_code == 200, path
    responses = [
        framer.post(f"/sites/{site_id}", data={**SITE, "name": "변경"}),
        framer.post(f"/sites/{site_id}/delete"),
        framer.post("/schedule", data={"site_id": site_id, **WORK}),
        framer.post("/judgments/run", data={"site_id": site_id}),
        add_member(framer, site_id, OUTSIDER["email"], "viewer"),
    ]
    assert [r.status_code for r in responses] == [403] * 5
    assert session.scalar(select(WorkItem.id)) is None


def test_member_page_hides_emails_and_controls_from_non_coordinators(
    client: TestClient, browser: Browser, site_id: int
) -> None:
    framer = browser(SUB_USER)
    add_member(client, site_id, SUB_USER["email"], "viewer")

    html = framer.get(f"/sites/{site_id}/members").text

    assert "가상건설" in html and "가상골조" in html and "협력업체" in html
    assert DEFAULT_USER["email"] not in html
    assert "권한 회수" not in html and 'name="email"' not in html
    site_page = framer.get(f"/sites?site_id={site_id}").text
    assert "열람 중" in site_page and ">저장</button>" not in site_page


def test_coordinator_must_belong_to_prime_company(
    client: TestClient, browser: Browser, site_id: int, session: Session
) -> None:
    browser(SUB_USER)
    colleague = colleague_of_default_user(session)

    refused = add_member(client, site_id, SUB_USER["email"], "coordinator")
    accepted = add_member(client, site_id, colleague, "coordinator")

    assert refused.status_code == 422 and "원청 소속" in refused.text
    assert accepted.status_code == 303
    assert active_membership(session, SUB_USER["email"], site_id) is None


@pytest.mark.parametrize(
    ("email", "role", "message"),
    [
        ("nobody@example.com", "viewer", "가입한 사용자"),
        (DEFAULT_USER["email"], "viewer", "이미 이 현장에 참여 중"),
        (SUB_USER["email"], "owner", "역할을 고르세요"),
    ],
)
def test_invalid_member_additions_are_explained(
    client: TestClient, browser: Browser, site_id: int, email: str, role: str, message: str
) -> None:
    browser(SUB_USER)

    response = add_member(client, site_id, email, role)

    assert response.status_code == 422 and message in response.text


def test_revoked_member_loses_access_on_next_request_and_history_is_kept(
    client: TestClient, browser: Browser, site_id: int, session: Session
) -> None:
    framer = browser(SUB_USER)
    add_member(client, site_id, SUB_USER["email"], "assignee")
    membership = active_membership(session, SUB_USER["email"], site_id)
    assert membership is not None and framer.get(f"/sites?site_id={site_id}").status_code == 200

    response = client.post(f"/sites/{site_id}/members/{membership.id}/revoke")

    assert response.status_code == 200 and "권한을 회수했습니다" in response.text
    assert framer.get(f"/sites?site_id={site_id}").status_code == 404
    session.refresh(membership)
    assert membership.revoked_at == FIXED_NOW and membership.revoked_by_user_id is not None
    # 다시 추가하면 새 행이 생기고 이전 회수 기록은 그대로 남는다
    assert add_member(client, site_id, SUB_USER["email"], "viewer").status_code == 303
    assert len(session.scalars(select(ProjectMembership).where(
        ProjectMembership.user_id == membership.user_id)).all()) == 2  # fmt: skip


def test_last_coordinator_cannot_be_revoked(
    client: TestClient, site_id: int, session: Session
) -> None:
    own = active_membership(session, DEFAULT_USER["email"], site_id)
    assert own is not None

    refused = client.post(f"/sites/{site_id}/members/{own.id}/revoke")
    add_member(client, site_id, colleague_of_default_user(session), "coordinator")
    allowed = client.post(f"/sites/{site_id}/members/{own.id}/revoke", follow_redirects=False)

    assert refused.status_code == 422 and "마지막 조정자" in refused.text
    assert (allowed.status_code, allowed.headers["location"]) == (303, "/sites")
    assert client.get(f"/sites?site_id={site_id}").status_code == 404


def test_revoke_with_membership_of_another_site_is_refused(
    client: TestClient, browser: Browser, site_id: int, session: Session
) -> None:
    outsider = browser(OUTSIDER)
    other_site = add_site(outsider, name="무관현장")
    foreign = active_membership(session, OUTSIDER["email"], other_site)
    assert foreign is not None

    response = client.post(f"/sites/{site_id}/members/{foreign.id}/revoke")

    assert response.status_code == 404
    assert active_membership(session, OUTSIDER["email"], other_site) is not None


def test_run_all_only_runs_sites_i_coordinate(
    client: TestClient, browser: Browser, site_id: int, session: Session
) -> None:
    framer = browser(SUB_USER)
    add_member(client, site_id, SUB_USER["email"], "assignee")
    own_site = add_site(framer, name="골조 자체 현장")
    for target in (site_id, own_site):
        client_for = client if target == site_id else framer
        tomorrow = {**WORK, "work_date": "2026-10-05"}
        client_for.post("/schedule", data={"site_id": target, **tomorrow})

    framer.post("/judgments/run-all")

    run_sites = set(session.scalars(select(JudgmentRun.site_id)))
    assert run_sites == {own_site}


def test_database_rejects_membership_pointing_at_another_sites_participant(
    client: TestClient, browser: Browser, site_id: int, session: Session
) -> None:
    outsider = browser(OUTSIDER)
    other_site = add_site(outsider, name="무관현장")
    participant = session.scalars(
        select(ProjectParticipant).where(ProjectParticipant.site_id == other_site)
    ).one()
    user = auth_service.find_user_by_email(session, OUTSIDER["email"])
    assert user is not None

    session.add(
        ProjectMembership(
            site_id=site_id,  # 참여 업체는 other_site 소속
            participant_id=participant.id,
            user_id=user.user_id,
            role="viewer",
            created_at=FIXED_NOW,
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_database_allows_only_one_prime_per_site(
    client: TestClient, browser: Browser, site_id: int, session: Session
) -> None:
    browser(OUTSIDER)
    user = auth_service.find_user_by_email(session, OUTSIDER["email"])
    assert user is not None

    session.add(
        ProjectParticipant(site_id=site_id, organization_id=user.organization_id, kind="prime")
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_grant_existing_site_requires_explicit_user_and_respects_prime(
    client: TestClient, browser: Browser, site_id: int, session: Session
) -> None:
    # 0010 이전에 만든 현장처럼 참여 기록을 지운다.
    session.execute(text("DELETE FROM project_participants"))
    session.commit()
    assert client.get(f"/sites?site_id={site_id}").status_code == 404
    browser(OUTSIDER)

    message = teams_service.grant_existing_site(session, site_id, DEFAULT_USER["email"], FIXED_NOW)

    assert "조정자로 지정" in message
    assert client.get(f"/sites?site_id={site_id}").status_code == 200
    with pytest.raises(ValueError, match="원청 회사 소속이 아님"):
        teams_service.grant_existing_site(session, site_id, OUTSIDER["email"], FIXED_NOW)
    with pytest.raises(ValueError, match="없는 현장"):
        teams_service.grant_existing_site(session, 9999, OUTSIDER["email"], FIXED_NOW)


def test_refusals_render_the_html_page_not_json(
    client: TestClient, browser: Browser, site_id: int
) -> None:
    framer = browser(SUB_USER)
    add_member(client, site_id, SUB_USER["email"], "viewer")

    forbidden = framer.post("/judgments/run", data={"site_id": site_id})
    missing = browser(OUTSIDER).get(f"/sites?site_id={site_id}")

    assert forbidden.status_code == 403 and "권한이 없습니다" in forbidden.text
    assert missing.status_code == 404 and "찾을 수 없습니다" in missing.text
    assert "text/html" in missing.headers["content-type"]


def test_coordinator_only_controls_are_hidden_from_other_roles(
    client: TestClient, browser: Browser, site_id: int
) -> None:
    framer = browser(SUB_USER)
    add_member(client, site_id, SUB_USER["email"], "assignee")
    client.post("/schedule", data={"site_id": site_id, **WORK})
    pages = {
        "home": "/home",
        "dashboard": f"/dashboard?site_id={site_id}",
        "schedule": f"/schedule?site_id={site_id}&day={WORK['work_date']}",
    }
    controls = ('action="/judgments/run"', 'action="/judgments/run-all"',
                "type=\"button\" data-open-add", "/delete\"")  # fmt: skip

    def shown(c: TestClient) -> set[str]:
        html = " ".join(c.get(p).text for p in pages.values())
        return {control for control in controls if control in html}

    assert shown(client) == set(controls)
    assert shown(framer) == set()
