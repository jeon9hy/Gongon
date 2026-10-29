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

PROTECTED_PAGES = ("/dashboard", "/schedule", "/judgments", "/sites", "/judgments/1")
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


def test_anonymous_home_visit_lands_on_welcome(anonymous_client: TestClient) -> None:
    response = anonymous_client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/welcome"
    html = anonymous_client.get("/welcome").text
    assert 'href="/signup"' in html and 'href="/login"' in html
    assert 'aria-label="주 메뉴"' not in html


def test_welcome_is_the_service_intro_leading_into_the_pc_app(
    anonymous_client: TestClient, client: TestClient
) -> None:
    html = anonymous_client.get("/welcome").text
    assert 'id="why"' in html and 'id="where"' in html  # 소개 구역이 한 화면에 이어진다(D-110)
    assert "공온 열기" not in html

    signed_in = client.get("/welcome", follow_redirects=False)
    assert signed_in.status_code == 200
    assert 'href="/">공온 열기' in signed_in.text and 'href="/signup"' not in signed_in.text


def test_old_about_address_goes_to_the_intro(anonymous_client: TestClient) -> None:
    response = anonymous_client.get("/about", follow_redirects=False)

    assert response.status_code == 308 and response.headers["location"] == "/welcome"


def test_pc_app_bar_links_back_to_the_intro(client: TestClient) -> None:
    assert 'class="appbar__about" href="/welcome"' in client.get("/sites").text


def test_app_shell_skips_the_intro(anonymous_client: TestClient) -> None:
    shell = {"user-agent": "Mozilla/5.0 (Linux; Android 14) GongonApp/1"}
    response = anonymous_client.get("/", headers=shell, follow_redirects=False)

    assert response.status_code == 303 and response.headers["location"] == "/login"
    # 휴대폰 브라우저는 앱 껍데기가 아니므로 소개를 본다
    phone = {"user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Mobile"}
    assert (
        anonymous_client.get("/", headers=phone, follow_redirects=False).headers["location"]
        == "/welcome"
    )


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

    assert response.headers["location"] == "/welcome"
    assert client.get("/sites", follow_redirects=False).status_code == 303


def test_deactivated_user_loses_existing_session(client: TestClient, session: Session) -> None:
    session.execute(update(User).values(is_active=False))
    session.commit()

    assert client.get("/sites", follow_redirects=False).status_code == 303


def test_layout_shows_who_is_signed_in(client: TestClient) -> None:
    html = client.get("/sites").text

    # 이름 메뉴(D-064): 이름·회사, 내 정보·공온 가이드·로그아웃
    menu = html.split('<details class="menu usermenu">')[1].split("</details>")[0]
    assert "<strong>테스트 조정자</strong><span>가상건설</span>" in menu
    assert 'href="/me"' in menu and 'href="/guide"' in menu and 'action="/logout"' in menu


def test_login_page_has_no_app_menu(anonymous_client: TestClient) -> None:
    html = anonymous_client.get("/login").text

    assert 'aria-label="주 메뉴"' not in html and 'action="/login"' in html


@pytest.mark.parametrize("path", ["/login", "/signup"])
def test_signed_in_user_going_back_to_auth_pages_is_sent_home(
    client: TestClient, path: str
) -> None:
    response = client.get(path, follow_redirects=False)

    assert response.status_code == 303 and response.headers["location"] == "/"


def test_html_pages_are_not_stored_so_back_rechecks_the_session(
    client: TestClient, anonymous_client: TestClient
) -> None:
    assert client.get("/sites").headers["cache-control"] == "no-store"
    assert anonymous_client.get("/login").headers["cache-control"] == "no-store"
    assert "no-store" not in client.get("/static/gongon.css").headers.get("cache-control", "")
