"""현장 게시 화면(C11, D-067). 가상 현장·가상 계정만 쓴다."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.features.schedules.models import WorkItem
from tests.app.features.changes.test_changes import (
    OUTSIDER,
    SITE,
    case_id_from,
    confirm,
    item_of,
    propose,
    revision,
)
from tests.conftest import Browser
from tests.helpers import add_site_with_work

TV = {
    "email": "tv@example.com",
    "display_name": "현장 TV",
    "organization_name": "현장TV",
    "password": "tv-password-123",
}


@pytest.fixture
def item(client: TestClient, session: Session) -> WorkItem:
    add_site_with_work(client, SITE)
    return item_of(session)


@pytest.fixture
def tv(client: TestClient, browser: Browser, item: WorkItem) -> TestClient:
    screen = browser(TV)
    added = client.post(
        f"/sites/{item.site_id}/members", data={"email": TV["email"], "role": "board"}
    )
    assert added.status_code == 200
    return screen


def test_board_account_sees_only_the_board(tv: TestClient, item: WorkItem) -> None:
    home = tv.get("/", follow_redirects=False)
    assert home.status_code == 303 and home.headers["location"] == "/board"
    page = tv.get(f"/board/{item.site_id}").text
    assert "작업 여부는 반장·소장 지시를 따릅니다." in page
    assert 'aria-label="주 메뉴"' not in page and "철골 작업" in page
    # 다른 화면·쓰기는 열리지 않는다
    assert tv.get(f"/schedule?site_id={item.site_id}").status_code == 404
    assert tv.get(f"/sites/{item.site_id}/members").status_code in (403, 404)
    assert tv.get(f"/chat/{item.site_id}").status_code == 403
    assert tv.post(f"/chat/{item.site_id}/messages", data={"body": "x"}).status_code == 403


def test_board_hides_contacts_and_shows_todays_confirmed_change(
    client: TestClient, session: Session, tv: TestClient, item: WorkItem
) -> None:
    client.post(
        f"/sites/{item.site_id}/participants/{_prime(session, item)}/contacts",
        data={"contact_name": "펌프 기사", "phone": "010-0000-0009", "memo": "비밀 메모"},
    )
    case_id = case_id_from(propose(client, item))
    confirm(client, item, case_id, revision(session).id)

    page = tv.get(f"/board/{item.site_id}").text

    assert "오늘 바뀐 일정" in page and "→ 10/06(화) 10:00-13:00" in page
    assert "010-0000-0009" not in page and "비밀 메모" not in page


def test_outsider_cannot_open_the_board(browser: Browser, item: WorkItem) -> None:
    assert browser(OUTSIDER).get(f"/board/{item.site_id}").status_code == 404


def _prime(session: Session, item: WorkItem) -> int:
    from sqlalchemy import select

    from app.features.teams.models import ProjectParticipant

    found = session.scalar(
        select(ProjectParticipant.id).where(
            ProjectParticipant.site_id == item.site_id, ProjectParticipant.kind == "prime"
        )
    )
    assert found is not None
    return found
