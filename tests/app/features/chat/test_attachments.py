"""대화방 첨부(D-111): 사진·연락처·조치(변경 건은 test_chat). 가상 현장·가상 회사만 쓴다."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.features.auth.models import User
from app.features.chat import service
from app.features.chat.models import SiteMessage
from app.features.schedules.models import WorkItem
from app.features.teams.models import ParticipantContact, ProjectParticipant
from tests.app.features.changes.test_changes import OUTSIDER, SITE, SUB_USER, VIEWER, item_of, join
from tests.conftest import FIXED_NOW, Browser
from tests.helpers import add_site_with_work

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64  # 앞부분만 PNG인 시험용 바이트(그림 내용은 보지 않는다)


@pytest.fixture
def item(client: TestClient, session: Session) -> WorkItem:
    add_site_with_work(client, SITE)
    return item_of(session)


def send(
    c: TestClient,
    site_id: int,
    body: str = "",
    files: dict[str, tuple[str, bytes, str]] | None = None,
    extra: dict[str, str] | None = None,
) -> Any:
    return c.post(
        f"/chat/{site_id}/messages",
        data={"body": body, **(extra or {})},
        files=files,
        follow_redirects=False,
    )


def last(session: Session) -> SiteMessage:
    session.expire_all()
    return session.scalars(select(SiteMessage).order_by(SiteMessage.id.desc())).first()  # type: ignore[return-value]


def add_contact(session: Session, site_id: int, phone: str = "010-0000-1234") -> int:
    prime = session.scalars(
        select(ProjectParticipant).where(ProjectParticipant.site_id == site_id)
    ).first()
    assert prime is not None
    contact = ParticipantContact(
        site_id=site_id,
        participant_id=prime.id,
        name="[가상] 김반장",
        job_title="반장",
        phone=phone,
        created_at=FIXED_NOW,
        created_by_user_id=session.scalars(select(User.id)).first(),
    )
    session.add(contact)
    session.commit()
    return contact.id


def test_photo_is_saved_and_only_site_members_can_open_it(
    client: TestClient, browser: Browser, session: Session, item: WorkItem
) -> None:
    framer = join(client, browser, item.site_id, SUB_USER, "assignee")

    assert (
        send(client, item.site_id, files={"photo": ("현장.png", PNG, "image/png")}).status_code
        == 303
    )
    message = last(session)
    assert message.photo_type == "image/png" and message.body == ""
    url = f"/chat/{item.site_id}/photos/{message.id}"

    shown = framer.get(url)
    assert shown.status_code == 200 and shown.content == PNG
    assert (
        shown.headers["content-type"] == "image/png" and "private" in shown.headers["cache-control"]
    )
    assert browser(OUTSIDER).get(url).status_code == 404
    assert url in framer.get(f"/chat/{item.site_id}").text
    phone = {"user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Mobile"}
    assert "나: 사진" in client.get("/chat", headers=phone).text  # 방 목록 미리보기(카톡처럼)


@pytest.mark.parametrize(
    ("kind", "error"), [("not-image", "사진(JPG·PNG·GIF·WebP)만"), ("over-limit", "10MB까지")]
)
def test_photo_type_and_size_limits(
    client: TestClient, session: Session, item: WorkItem, kind: str, error: str
) -> None:
    if kind == "not-image":
        data = b"not an image at all"
    else:  # 한도보다 1바이트 큼
        data = PNG + b"\x00" * (service.PHOTO_MAX_BYTES - len(PNG) + 1)
    response = send(client, item.site_id, files={"photo": ("a.png", data, "image/png")})

    assert response.status_code == 422 and error in response.text
    assert last(session) is None


def test_photo_exactly_at_the_size_limit_is_accepted(
    client: TestClient, session: Session, item: WorkItem
) -> None:
    data = PNG + b"\x00" * (service.PHOTO_MAX_BYTES - len(PNG))

    assert (
        send(client, item.site_id, files={"photo": ("a.png", data, "image/png")}).status_code == 303
    )
    assert last(session).photo_bytes == service.PHOTO_MAX_BYTES


def test_deleted_message_photo_is_no_longer_served(
    client: TestClient, session: Session, item: WorkItem
) -> None:
    send(client, item.site_id, files={"photo": ("a.png", PNG, "image/png")})
    message = last(session)
    client.post(f"/chat/{item.site_id}/messages/{message.id}/delete")

    assert client.get(f"/chat/{item.site_id}/photos/{message.id}").status_code == 404


def test_contact_card_hides_phone_from_viewers(
    client: TestClient, browser: Browser, session: Session, item: WorkItem
) -> None:
    contact_id = add_contact(session, item.site_id)
    viewer = join(client, browser, item.site_id, VIEWER, "viewer")

    assert send(client, item.site_id, extra={"contact_id": str(contact_id)}).status_code == 303
    assert last(session).linked_contact_id == contact_id

    assert "tel:010-0000-1234" in client.get(f"/chat/{item.site_id}").text
    seen_by_viewer = viewer.get(f"/chat/{item.site_id}").text
    assert "[가상] 김반장" in seen_by_viewer and "010-0000-1234" not in seen_by_viewer


@pytest.mark.parametrize("field", ["contact_id", "action_id", "case_id"])
def test_attachment_must_belong_to_the_site(
    client: TestClient, session: Session, item: WorkItem, field: str
) -> None:
    response = send(client, item.site_id, "같이 봐 주세요", extra={field: "999999"})

    assert response.status_code == 422 and "이 현장의 것을 골라 주세요" in response.text
    assert last(session) is None


def test_one_attachment_per_message_and_empty_message_is_refused(
    client: TestClient, session: Session, item: WorkItem
) -> None:
    contact_id = add_contact(session, item.site_id)

    both = send(
        client,
        item.site_id,
        extra={"contact_id": str(contact_id)},
        files={"photo": ("a.png", PNG, "image/png")},
    )
    empty = send(client, item.site_id, "   ")

    assert both.status_code == 422 and "하나만" in both.text
    assert empty.status_code == 422 and "첨부를 골라" in empty.text
    assert last(session) is None
