"""서비스 소개 → 내 현장 → PC 웹 앱(D-110, 슬랙 방식)."""

from fastapi.testclient import TestClient

from tests.app.features.judgments.test_home_today import make_site
from tests.conftest import DEFAULT_USER

IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Mobile"
SHELL = "Mozilla/5.0 (Linux; Android 14) GongonApp/1"


def test_intro_comes_first_before_login(anonymous_client: TestClient) -> None:
    page = anonymous_client.get("/")

    assert page.status_code == 200
    assert 'id="why"' in page.text and 'id="where"' in page.text
    assert 'href="/signup"' in page.text and 'href="/login"' in page.text
    assert 'aria-label="주 메뉴"' not in page.text


def test_signed_in_pc_still_sees_intro_and_opens_the_app_from_a_site(client: TestClient) -> None:
    site_id = make_site(client)

    page = client.get("/", follow_redirects=False)

    assert page.status_code == 200 and 'id="why"' in page.text
    assert f'href="/home?site_id={site_id}"' in page.text and 'href="/home"' in page.text
    assert 'href="/signup"' not in page.text
    assert client.get(f"/home?site_id={site_id}").status_code == 200


def test_site_list_shows_only_my_sites(client: TestClient, anonymous_client: TestClient) -> None:
    make_site(client)
    anonymous_client.post("/signup", data={**DEFAULT_USER, "email": "other@example.com"})

    assert "/home?site_id=" not in anonymous_client.get("/").text


def test_phone_app_skips_the_intro(client: TestClient, anonymous_client: TestClient) -> None:
    signed_in = client.get("/", headers={"user-agent": IPHONE}, follow_redirects=False)
    assert signed_in.status_code == 303 and signed_in.headers["location"] == "/home"

    shell = anonymous_client.get("/", headers={"user-agent": SHELL}, follow_redirects=False)
    assert shell.status_code == 303 and shell.headers["location"] == "/login"
    # 로그인 전 휴대폰 브라우저는 소개를 본다
    assert anonymous_client.get("/", headers={"user-agent": IPHONE}).status_code == 200


def test_old_addresses_and_app_bar_lead_to_the_intro(
    client: TestClient, anonymous_client: TestClient
) -> None:
    for old in ("/welcome", "/about"):
        response = anonymous_client.get(old, follow_redirects=False)
        assert response.status_code == 308 and response.headers["location"] == "/"
    assert 'class="appbar__about" href="/"' in client.get("/sites").text
