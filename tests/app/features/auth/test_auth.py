"""로그인·세션·같은 출처 검사(C03-1, D-057)."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.core.clock import now_kst
from app.features.auth import service
from app.features.auth.models import User
from tests.conftest import DEFAULT_USER, FIXED_NOW

PROTECTED_PAGES = ("/", "/dashboard", "/schedule", "/judgments", "/sites", "/judgments/1")
SITE = {
    "name": "가상현장",
    "lot_address": "서울 중구 태평로1가 31",
    "latitude": "37.5665",
    "longitude": "126.9780",
    "work_start": "07:00",
    "work_end": "17:00",
    "work_start_date": "2026-10-01",
    "work_end_date": "2026-12-31",
    "work_types": ["철골 작업"],
}


def signup(client: TestClient, **changes: str) -> int:
    return client.post(
        "/signup", data={**DEFAULT_USER, **changes}, follow_redirects=False
    ).status_code


def site_count(session: Session) -> int:
    return session.scalar(text("SELECT count(*) FROM sites")) or 0


@pytest.mark.parametrize("path", PROTECTED_PAGES)
def test_pages_send_anonymous_visitor_to_login_with_return_path(
    anonymous_client: TestClient, path: str
) -> None:
    response = anonymous_client.get(f"{path}?site_id=3", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login?next=" + f"{path}?site_id=3".replace(
        "/", "%2F"
    ).replace("?", "%3F").replace("=", "%3D")


def test_anonymous_write_is_not_executed(anonymous_client: TestClient, session: Session) -> None:
    response = anonymous_client.post("/sites", data=SITE, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")
    assert site_count(session) == 0


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": ""},  # Origin·Referer 모두 없음
        {"Origin": "https://evil.example"},
        {"Origin": "", "Referer": "https://evil.example/form"},
    ],
)
def test_signed_in_write_from_other_or_unknown_origin_is_rejected(
    client: TestClient, session: Session, headers: dict[str, str]
) -> None:
    response = client.post("/sites", data=SITE, headers=headers, follow_redirects=False)

    assert response.status_code == 403
    assert site_count(session) == 0


def test_same_origin_referer_is_accepted_when_origin_missing(
    client: TestClient, session: Session
) -> None:
    response = client.post(
        "/sites",
        data=SITE,
        headers={"Origin": "", "Referer": "http://testserver/sites"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert site_count(session) == 1


def test_login_form_is_also_origin_checked(anonymous_client: TestClient) -> None:
    signup(anonymous_client)
    anonymous_client.cookies.clear()

    response = anonymous_client.post(
        "/login",
        data={"email": DEFAULT_USER["email"], "password": DEFAULT_USER["password"]},
        headers={"Origin": "https://evil.example"},
        follow_redirects=False,
    )

    assert response.status_code == 403
    assert service.SESSION_COOKIE not in response.cookies


def test_signup_sets_protected_session_cookie_and_stores_only_hashes(
    anonymous_client: TestClient, session: Session
) -> None:
    response = anonymous_client.post("/signup", data=DEFAULT_USER, follow_redirects=False)

    cookie = response.headers["set-cookie"]
    assert response.status_code == 303
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Max-Age=43200" in cookie
    token = anonymous_client.cookies[service.SESSION_COOKIE]
    stored = session.execute(text("SELECT token_sha256 FROM auth_sessions")).scalars().all()
    assert stored == [service._token_hash(token)] and token not in stored
    user = session.scalars(select(User)).one()
    assert DEFAULT_USER["password"] not in user.password_hash
    assert service.verify_password(DEFAULT_USER["password"], user.password_hash)
    assert not service.verify_password("correct-horse-batterx", user.password_hash)


@pytest.mark.parametrize(("password", "accepted"), [("a" * 9, False), ("a" * 10, True)])
def test_password_length_boundary(
    anonymous_client: TestClient, password: str, accepted: bool
) -> None:
    assert signup(anonymous_client, password=password) == (303 if accepted else 422)


def test_duplicate_email_is_rejected_regardless_of_case(anonymous_client: TestClient) -> None:
    assert signup(anonymous_client) == 303

    response = anonymous_client.post(
        "/signup", data={**DEFAULT_USER, "email": " Coordinator@Example.COM "}
    )

    assert response.status_code == 422
    assert "이미 가입한 이메일" in response.text


def test_wrong_password_is_rejected_without_session(anonymous_client: TestClient) -> None:
    signup(anonymous_client)
    anonymous_client.cookies.clear()

    response = anonymous_client.post(
        "/login", data={"email": DEFAULT_USER["email"], "password": "wrong-password!"}
    )

    assert response.status_code == 401
    assert service.SESSION_COOKIE not in anonymous_client.cookies


def test_login_returns_to_requested_page(anonymous_client: TestClient) -> None:
    signup(anonymous_client)
    anonymous_client.cookies.clear()

    response = anonymous_client.post(
        "/login",
        data={
            "email": DEFAULT_USER["email"].upper(),
            "password": DEFAULT_USER["password"],
            "next": "/judgments?page=2",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/judgments?page=2"
    assert anonymous_client.get("/judgments", follow_redirects=False).status_code == 200


@pytest.mark.parametrize(
    "target", ["//evil.example/x", "https://evil.example", "/\\evil.example", "", "sites"]
)
def test_return_path_never_leaves_the_app(target: str) -> None:
    assert service.safe_next(target) == "/"


@pytest.mark.parametrize(
    ("elapsed", "signed_in"),
    [(timedelta(hours=12) - timedelta(seconds=1), True), (timedelta(hours=12), False)],
)
def test_session_expires_after_twelve_hours(
    client: TestClient, elapsed: timedelta, signed_in: bool
) -> None:
    app = client.app
    app.dependency_overrides[now_kst] = lambda: FIXED_NOW + elapsed  # type: ignore[attr-defined]

    response = client.get("/sites", follow_redirects=False)

    assert response.status_code == (200 if signed_in else 303)


def test_logout_invalidates_the_token_on_the_server(client: TestClient) -> None:
    token = client.cookies[service.SESSION_COOKIE]

    response = client.post("/logout", follow_redirects=False)
    client.cookies.set(service.SESSION_COOKIE, token)  # 쿠키를 지우지 않고 다시 보내는 경우

    assert response.headers["location"] == "/login?signed_out=true"
    assert client.get("/sites", follow_redirects=False).status_code == 303


def test_deactivated_user_loses_existing_session(client: TestClient, session: Session) -> None:
    session.execute(update(User).values(is_active=False))
    session.commit()

    assert client.get("/sites", follow_redirects=False).status_code == 303


def test_layout_shows_who_is_signed_in(client: TestClient) -> None:
    html = client.get("/sites").text

    assert "테스트 조정자 · 가상건설" in html and 'action="/logout"' in html


def test_login_page_has_no_app_menu(anonymous_client: TestClient) -> None:
    html = anonymous_client.get("/login").text

    assert 'aria-label="주 메뉴"' not in html and 'action="/login"' in html
