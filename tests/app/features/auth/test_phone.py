"""휴대폰 번호 가입·번호로 현장 초대(C04-13, D-073). 번호는 모두 가상 번호다. 문자 인증은 없다."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.features.auth import service
from app.features.auth.models import User
from app.features.teams.models import ProjectMembership
from tests.conftest import DEFAULT_USER, Browser

SITE = {
    "name": "가상A현장",
    "road_address": "서울 중구 세종대로 110",
    "latitude": "37.5665",
    "longitude": "126.9780",
    "work_start_date": "2026-10-01",
    "work_end_date": "2026-12-31",
}
FRAME_USER = {
    "email": "frame@example.com",
    "display_name": "골조 반장",
    "organization_name": "가상골조",
    "password": "frame-password-1",
    "phone": "010-2222-3333",
}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("010-1234-5678", "01012345678"),
        ("010 1234 5678", "01012345678"),
        ("+82 10-1234-5678", "01012345678"),
        ("8201012345678", "01012345678"),
        ("011-123-4567", "0111234567"),  # 옛 10자리 번호
        ("010-1234-567", None),  # 한 자리 모자람
        ("010-1234-56789", None),  # 한 자리 넘침
        ("02-123-4567", None),  # 휴대폰이 아님
        ("", None),
    ],
)
def test_phone_is_normalized_to_digits_or_rejected(raw: str, expected: str | None) -> None:
    assert service.normalize_phone(raw) == expected


def test_signup_requires_valid_unique_phone(anonymous_client: TestClient, session: Session) -> None:
    missing = {**DEFAULT_USER, "phone": ""}
    assert anonymous_client.post("/signup", data=missing).status_code == 422
    assert (
        anonymous_client.post("/signup", data=DEFAULT_USER, follow_redirects=False).status_code
        == 303
    )
    saved = session.scalar(select(User.phone).where(User.email == DEFAULT_USER["email"]))
    assert saved == "01012345678"

    same_number = {**DEFAULT_USER, "email": "other@example.com", "phone": "01012345678"}
    response = anonymous_client.post("/signup", data=same_number)

    assert response.status_code == 422 and "이미 가입한 휴대폰 번호" in response.text


def test_coordinator_adds_member_by_phone(
    client: TestClient, browser: Browser, session: Session
) -> None:
    site_id = int(
        client.post("/sites", data=SITE, follow_redirects=False)
        .headers["location"].split("site_id=")[1].split("&")[0]
    )  # fmt: skip
    browser(FRAME_USER)

    response = client.post(
        f"/sites/{site_id}/members",
        data={"email": "010 2222 3333", "role": "assignee"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    frame = service.find_user(session, "01022223333")
    assert frame is not None and frame.email == FRAME_USER["email"]
    roles = session.scalars(
        select(ProjectMembership.role).where(
            ProjectMembership.site_id == site_id, ProjectMembership.user_id == frame.user_id
        )
    ).all()
    assert roles == ["assignee"]


def test_unknown_phone_is_not_added(client: TestClient) -> None:
    site_id = int(
        client.post("/sites", data=SITE, follow_redirects=False)
        .headers["location"].split("site_id=")[1].split("&")[0]
    )  # fmt: skip

    response = client.post(
        f"/sites/{site_id}/members", data={"email": "010-9999-0000", "role": "assignee"}
    )

    assert response.status_code == 422 and "휴대폰 번호나 이메일" in response.text


def test_me_changes_phone_and_rejects_number_in_use(
    client: TestClient, browser: Browser, session: Session
) -> None:
    browser(FRAME_USER)

    taken = client.post("/me/phone", data={"phone": FRAME_USER["phone"]})
    changed = client.post("/me/phone", data={"phone": "010-4444-5555"}, follow_redirects=False)

    assert taken.status_code == 422 and "이미 쓰는 번호" in taken.text
    assert changed.status_code == 303
    session.expire_all()
    me = session.scalar(select(User).where(User.email == DEFAULT_USER["email"]))
    assert me is not None and me.phone == "01044445555" and me.phone_verified_at is None
    assert "010-4444-5555" in client.get("/me").text
