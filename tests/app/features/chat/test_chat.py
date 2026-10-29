"""현장 대화방(C12, D-071). 가상 현장·가상 회사만 쓴다."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.features.chat.models import SiteMessage
from app.features.schedules.models import WorkItem
from tests.app.features.changes.test_changes import (
    OUTSIDER,
    SITE,
    SUB_USER,
    case_id_from,
    item_of,
    join,
    propose,
)
from tests.conftest import Browser
from tests.helpers import add_site_with_work


@pytest.fixture
def item(client: TestClient, session: Session) -> WorkItem:
    add_site_with_work(client, SITE)
    return item_of(session)


def send(c: TestClient, site_id: int, body: str, **extra: Any) -> Any:
    return c.post(f"/chat/{site_id}/messages", data={"body": body, **extra}, follow_redirects=False)


def messages(session: Session) -> list[SiteMessage]:
    session.expire_all()
    return list(session.scalars(select(SiteMessage).order_by(SiteMessage.id)))


def test_members_talk_and_outsiders_cannot_see_the_room(
    client: TestClient, browser: Browser, session: Session, item: WorkItem
) -> None:
    framer = join(client, browser, item.site_id, SUB_USER, "assignee")
    outsider = browser(OUTSIDER)

    assert send(client, item.site_id, "내일 펌프 몇 시 도착이에요?").status_code == 303
    assert send(framer, item.site_id, "07시 도착 예정입니다").status_code == 303
    page = framer.get(f"/chat/{item.site_id}").text
    assert "내일 펌프 몇 시 도착이에요?" in page and "07시 도착 예정입니다" in page

    assert outsider.get(f"/chat/{item.site_id}").status_code == 404
    assert send(outsider, item.site_id, "몰래").status_code == 404
    assert outsider.get(f"/chat/{item.site_id}/messages?after=0").status_code == 404
    assert len(messages(session)) == 2


@pytest.mark.parametrize(("length", "ok"), [(0, False), (1, True), (1000, True), (1001, False)])
def test_message_length_limits(
    client: TestClient, session: Session, item: WorkItem, length: int, ok: bool
) -> None:
    response = send(client, item.site_id, "가" * length)

    assert (response.status_code == 303) is ok
    assert len(messages(session)) == (1 if ok else 0)


def test_linked_case_must_belong_to_the_site_and_shows_current_state(
    client: TestClient, browser: Browser, session: Session, item: WorkItem
) -> None:
    case_id = case_id_from(propose(client, item))
    other_site = browser(OUTSIDER)
    add_site_with_work(other_site, {**SITE, "name": "남의현장"})
    other_item = session.scalars(select(WorkItem).where(WorkItem.id != item.id)).one()
    other_case = case_id_from(propose(other_site, other_item))

    assert send(client, item.site_id, "남의 건", case_id=str(other_case)).status_code == 422
    assert send(client, item.site_id, "이 건 봐 주세요", case_id=str(case_id)).status_code == 303
    page = client.get(f"/chat/{item.site_id}").text
    assert f'href="/changes/{case_id}"' in page and "지금 v1 영향 검토" in page


def test_only_the_author_hides_a_message_and_the_row_is_kept(
    client: TestClient, browser: Browser, session: Session, item: WorkItem
) -> None:
    framer = join(client, browser, item.site_id, SUB_USER, "assignee")
    send(client, item.site_id, "잘못 보냄")
    message_id = messages(session)[0].id

    other = framer.post(f"/chat/{item.site_id}/messages/{message_id}/delete")
    assert other.status_code == 403
    mine = client.post(f"/chat/{item.site_id}/messages/{message_id}/delete", follow_redirects=False)
    assert mine.status_code == 303
    kept = messages(session)
    assert len(kept) == 1 and kept[0].deleted_at is not None
    page = framer.get(f"/chat/{item.site_id}").text
    assert "잘못 보냄" not in page and "삭제된 메시지예요." in page


def test_polling_returns_only_newer_messages(
    client: TestClient, session: Session, item: WorkItem
) -> None:
    send(client, item.site_id, "첫째")
    first = messages(session)[0].id
    send(client, item.site_id, "둘째")

    fragment = client.get(f"/chat/{item.site_id}/messages?after={first}").text

    assert "둘째" in fragment and "첫째" not in fragment


IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) Mobile/15E148"


def test_room_list_puts_latest_talk_first_with_preview_and_kakao_style_time(
    client: TestClient, browser: Browser, session: Session, item: WorkItem
) -> None:
    other = add_site_with_work(client, {**SITE, "name": "가상B현장"})
    quiet = add_site_with_work(client, {**SITE, "name": "가상C현장"})
    framer = join(client, browser, item.site_id, SUB_USER, "assignee")
    send(client, other, "B현장 먼저 보냄")
    send(framer, item.site_id, "줄\n바꿈 있는 답")  # 더 나중 메시지라 이 방이 맨 위
    # 어제·그 전 메시지는 시각을 직접 넣는다(FIXED_NOW = 10/04 15:00)
    old = messages(session)[0]
    old.created_at = old.created_at.replace(day=2)
    session.commit()

    page = client.get("/chat", headers={"user-agent": IPHONE}).text
    first, second, third = (page.index(n) for n in (SITE["name"], "가상B현장", "가상C현장"))

    assert first < second < third  # 대화 없는 방은 뒤
    assert "줄 바꿈 있는 답" in page and "오후 3:00" in page
    assert "나: B현장 먼저 보냄" in page and "10월 2일" in page
    assert page.count("아직 대화가 없어요") == 1
    assert quiet  # 대화가 없어도 목록에 있다


def test_app_room_has_back_to_list_and_hides_tab_bar(client: TestClient, item: WorkItem) -> None:
    send(client, item.site_id, "안녕하세요")

    room = client.get(f"/chat/{item.site_id}", headers={"user-agent": IPHONE}).text
    rooms = client.get("/chat", headers={"user-agent": IPHONE}).text

    assert 'class="mbar__back" href="/chat"' in room and '<nav class="tabbar"' not in room
    assert "안녕하세요" in room and "chat.js" in room
    assert '<nav class="tabbar"' in rooms and 'class="mroom"' in rooms
