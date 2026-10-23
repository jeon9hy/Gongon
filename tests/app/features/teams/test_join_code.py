"""현장 코드로 참여(C04-39, D-095).

현장을 만든 사람이 조정자이고, 그 현장 코드를 받은 가입자는 자기 회사 그대로 담당자로 들어온다.
코드는 조정자만 보고 바꿀 수 있다. 바꾸면 옛 코드는 막히고,
삭제한 현장·제외된 업체로는 참여하지 못한다.
"""

import re
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.features.teams.models import ProjectMembership, ProjectParticipant
from tests.app.features.teams.test_roster import add_site
from tests.conftest import Browser

WORKER = {
    "email": "worker@example.com",
    "display_name": "가상 반장",
    "organization_name": "가상철강",
    "password": "worker-password-1",
}


def code_of(client: TestClient, site_id: int) -> str:
    page = client.get(f"/sites/{site_id}/members").text
    found = re.search(r'id="join-code">([A-Z0-9]{4}-[A-Z0-9]{4})<', page)
    assert found, "조정자 화면에 현장 코드가 없다"
    return found.group(1)


def join(client: TestClient, code: str) -> Any:
    return client.post("/join", data={"code": code}, follow_redirects=False)


def test_code_joins_as_assignee_of_own_company_and_shows_the_site(
    client: TestClient, browser: Browser, session: Session
) -> None:
    site_id = add_site(client, "가상A현장")
    worker = browser(WORKER)

    response = join(worker, code_of(client, site_id).lower())  # 소문자도 받는다

    assert response.status_code == 303
    assert response.headers["location"] == f"/sites/{site_id}/members?done=joined"
    membership = session.scalars(
        select(ProjectMembership).where(
            ProjectMembership.site_id == site_id, ProjectMembership.role == "assignee"
        )
    ).one()
    participant = session.get(ProjectParticipant, membership.participant_id)
    assert participant is not None and participant.kind == "subcontractor"
    assert "가상A현장" in worker.get("/sites/switcher").text
    assert 'id="join-code"' not in worker.get(f"/sites/{site_id}/members").text  # 담당자는 못 본다


def test_joining_twice_keeps_one_membership(
    client: TestClient, browser: Browser, session: Session
) -> None:
    site_id = add_site(client)
    code = code_of(client, site_id)
    worker = browser(WORKER)

    join(worker, code)
    again = worker.post("/join", data={"code": code.replace("-", " ")}, follow_redirects=False)

    assert again.headers["location"].endswith("done=already")
    rows = session.scalars(select(ProjectMembership).where(ProjectMembership.site_id == site_id))
    assert len(list(rows)) == 2  # 만든 사람 + 참여한 사람


def test_wrong_or_renewed_code_is_refused(client: TestClient, browser: Browser) -> None:
    site_id = add_site(client)
    old = code_of(client, site_id)
    worker = browser(WORKER)

    assert join(worker, "ABCD").status_code == 422  # 자릿수 부족
    client.post(f"/sites/{site_id}/join-code")
    new = code_of(client, site_id)
    refused = worker.post("/join", data={"code": old})

    assert new != old
    assert refused.status_code == 422 and "맞는 현장 코드가 없어요" in refused.text
    assert "가상A현장" not in worker.get("/sites/switcher").text


def test_only_a_coordinator_can_renew_the_code(client: TestClient, browser: Browser) -> None:
    site_id = add_site(client)
    code = code_of(client, site_id)
    worker = browser(WORKER)
    join(worker, code)

    response = worker.post(f"/sites/{site_id}/join-code", follow_redirects=False)

    assert response.status_code == 403
    assert code_of(client, site_id) == code


def test_deleted_site_or_excluded_company_cannot_join(
    client: TestClient, browser: Browser, session: Session
) -> None:
    gone = add_site(client, "가상삭제현장")
    gone_code = code_of(client, gone)
    client.post(f"/sites/{gone}/delete")
    kept = add_site(client, "가상B현장")
    worker = browser(WORKER)
    join(worker, code_of(client, kept))
    membership = session.scalars(
        select(ProjectMembership).where(
            ProjectMembership.site_id == kept, ProjectMembership.role == "assignee"
        )
    ).one()
    client.post(f"/sites/{kept}/members/{membership.id}/revoke")
    client.post(f"/sites/{kept}/participants/{membership.participant_id}/end")

    deleted = worker.post("/join", data={"code": gone_code})
    excluded = worker.post("/join", data={"code": code_of(client, kept)})

    assert deleted.status_code == 422 and "맞는 현장 코드가 없어요" in deleted.text
    assert excluded.status_code == 422 and "제외된 업체" in excluded.text
