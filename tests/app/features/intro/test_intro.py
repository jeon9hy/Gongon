"""공온 서비스 사이트 → 내 현장 → PC 웹 앱(D-110, 슬랙 방식)."""

import pytest
from fastapi.testclient import TestClient

from tests.app.features.judgments.test_home_today import make_site
from tests.conftest import DEFAULT_USER

IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Mobile"
SHELL = "Mozilla/5.0 (Linux; Android 14) GongonApp/1"
FEATURES = ("changes", "actions", "schedule", "team", "chat")


def test_front_page_before_login_shows_features_and_sign_up(anonymous_client: TestClient) -> None:
    page = anonymous_client.get("/")

    assert page.status_code == 200
    assert 'href="/signup"' in page.text and 'href="/login"' in page.text
    for key in FEATURES:
        assert f'id="feature-{key}"' in page.text
    assert 'aria-label="주 메뉴"' not in page.text  # 앱 메뉴가 아니라 서비스 사이트 머리줄


def test_signed_in_front_page_picks_a_site_to_open_the_pc_app(client: TestClient) -> None:
    site_id = make_site(client)

    page = client.get("/", follow_redirects=False)

    assert page.status_code == 200 and "다시 만나서 반가워요" in page.text
    assert f'href="/home?site_id={site_id}"' in page.text and 'href="/home"' in page.text
    assert 'href="/join"' in page.text and 'action="/logout"' in page.text
    assert 'href="/signup"' not in page.text
    assert client.get(f"/home?site_id={site_id}").status_code == 200


def test_site_list_shows_only_my_sites(client: TestClient, anonymous_client: TestClient) -> None:
    make_site(client)
    anonymous_client.post(
        "/signup", data={**DEFAULT_USER, "email": "other@example.com", "phone": "010-9999-0000"}
    )

    page = anonymous_client.get("/").text
    assert "다시 만나서 반가워요" in page and "/home?site_id=" not in page


@pytest.mark.parametrize(
    ("path", "marker"),
    [
        ("/features", 'id="where"'),
        ("/collab", "협력업체 현장대리인"),
        ("/about", 'id="principles"'),
        ("/pricing", "시범 운영"),
    ],
)
def test_menu_items_are_their_own_pages(
    anonymous_client: TestClient, client: TestClient, path: str, marker: str
) -> None:
    page = anonymous_client.get(path)
    assert page.status_code == 200 and marker in page.text
    assert f'href="{path}' in page.text  # 머리줄·바닥글 링크
    assert 'href="/signup"' in page.text
    assert 'href="/signup"' not in client.get(path).text  # 로그인했으면 내 현장·로그아웃


def test_phone_app_skips_the_service_site(client: TestClient, anonymous_client: TestClient) -> None:
    signed_in = client.get("/", headers={"user-agent": IPHONE}, follow_redirects=False)
    assert signed_in.status_code == 303 and signed_in.headers["location"] == "/home"

    shell = anonymous_client.get("/", headers={"user-agent": SHELL}, follow_redirects=False)
    assert shell.status_code == 303 and shell.headers["location"] == "/login"
    # 로그인 전 휴대폰 브라우저는 서비스 사이트를 본다
    assert anonymous_client.get("/", headers={"user-agent": IPHONE}).status_code == 200


def test_old_welcome_address_and_app_bar_lead_to_the_service_site(
    client: TestClient, anonymous_client: TestClient
) -> None:
    response = anonymous_client.get("/welcome", follow_redirects=False)
    assert response.status_code == 308 and response.headers["location"] == "/"
    assert 'class="appbar__about" href="/"' in client.get("/sites").text


def test_footer_is_on_the_service_site_only_and_me_page_can_log_out(client: TestClient) -> None:
    make_site(client)

    assert 'class="sitefoot intro__foot"' in client.get("/").text
    assert "sitefoot" not in client.get("/home").text
    # 휴대폰 앱 화면에는 이름 메뉴가 없어 내 정보에서 로그아웃한다
    assert 'action="/logout"' in client.get("/me", headers={"user-agent": IPHONE}).text
