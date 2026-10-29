"""앱 화면/웹 화면 고르기(D-109): 같은 주소·권한에서 화면만 바뀐다."""

from datetime import date, time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from starlette.datastructures import Headers

from app.core.templating import app_variant
from app.core.ui_mode import UI_COOKIE, detect
from tests.app.features.judgments.test_home_today import make_site, put

IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) Mobile/15E148"
ANDROID_PHONE = "Mozilla/5.0 (Linux; Android 14; SM-S918N) Chrome/126.0 Mobile Safari/537.36"
ANDROID_TABLET = "Mozilla/5.0 (Linux; Android 14; SM-X710) Chrome/126.0 Safari/537.36"
IPAD = "Mozilla/5.0 (iPad; CPU OS 17_5 like Mac OS X) Mobile/15E148"
DESKTOP = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0 Safari/537.36"
SHELL = f"{ANDROID_TABLET} GongonApp/1"
APP_HTML = '<html lang="ko" data-ui="app"'


@pytest.mark.parametrize(
    ("agent", "mode"),
    [(IPHONE, "app"), (ANDROID_PHONE, "app"), (SHELL, "app"),
     (ANDROID_TABLET, "web"), (IPAD, "web"), (DESKTOP, "web"), ("", "web")],
)  # fmt: skip
def test_device_picks_app_only_for_phones_and_the_app_shell(agent: str, mode: str) -> None:
    assert detect(Headers({"user-agent": agent}), b"") == (mode, False)


def test_choice_in_address_beats_cookie_and_cookie_beats_device() -> None:
    phone_saved_web = Headers({"user-agent": IPHONE, "cookie": f"{UI_COOKIE}=web"})
    assert detect(phone_saved_web, b"") == ("web", False)
    assert detect(phone_saved_web, b"ui=app") == ("app", True)
    # 모르는 값은 무시하고 다음 순서로 정한다
    unknown = Headers({"user-agent": DESKTOP, "cookie": f"{UI_COOKIE}=tv"})
    assert detect(unknown, b"ui=tv") == ("web", False)


def test_app_variant_name() -> None:
    assert app_variant("judgments/home.html") == "judgments/app/home.html"
    assert app_variant("base.html") == "app/base.html"


def test_phone_gets_app_home_with_tab_bar_and_pc_gets_web_home(
    client: TestClient, session: Session
) -> None:
    site_id = make_site(client)
    put(session, site_id, date(2026, 10, 4), time(16), time(18), "거푸집 설치")

    web = client.get("/home", headers={"user-agent": DESKTOP}).text
    phone = client.get("/home", headers={"user-agent": IPHONE}).text

    assert APP_HTML not in web and 'class="appbar"' in web and '<nav class="tabbar"' not in web
    assert APP_HTML in phone and '<nav class="tabbar"' in phone and 'class="appbar"' not in phone
    assert "app.css" in phone and "app.css" not in web
    assert "msum" in phone and "거푸집 설치" in phone  # 같은 자료를 앱 화면으로


def test_choosing_pc_view_on_a_phone_is_remembered(client: TestClient) -> None:
    make_site(client)

    switched = client.get("/home?ui=web", headers={"user-agent": IPHONE})
    assert f"{UI_COOKIE}=web" in switched.headers["set-cookie"]
    assert APP_HTML not in switched.text
    # 쿠키가 남아 다음 화면도 웹 화면이다
    assert APP_HTML not in client.get("/schedule", headers={"user-agent": IPHONE}).text


def test_page_without_app_layout_falls_back_to_web_content_in_app_frame(client: TestClient) -> None:
    make_site(client)

    page = client.get("/team", headers={"user-agent": IPHONE})

    assert page.status_code == 200
    assert '<nav class="tabbar"' in page.text and 'aria-current="page"' in page.text


def test_app_view_keeps_access_rules(anonymous_client: TestClient) -> None:
    response = anonymous_client.get("/home", headers={"user-agent": IPHONE}, follow_redirects=False)
    assert response.status_code in (302, 303, 307)


def test_pc_web_never_gets_narrow_layout_but_modal_frames_and_app_do(client: TestClient) -> None:
    """PC 웹은 창을 줄여도 앱처럼 바뀌지 않는다. 좁은 배치는 앱 화면과 모달 안 화면(embed)만."""
    make_site(client)

    web = client.get("/schedule", headers={"user-agent": DESKTOP}).text
    modal = client.get("/sites?embed=1", headers={"user-agent": DESKTOP}).text
    phone = client.get("/schedule", headers={"user-agent": IPHONE}).text

    assert "data-narrow" not in web.split("<head>")[0]
    assert "data-narrow" in modal.split("<head>")[0]
    assert "data-narrow" in phone.split("<head>")[0]


@pytest.mark.parametrize("path", ["/actions", "/changes", "/team"])
def test_actions_changes_and_team_have_compact_phone_layouts(client: TestClient, path: str) -> None:
    """C13-1b·c·f: 휴대폰은 넓은 표 대신 한 줄 목록·칩을 쓴다(가로로 넘치는 웹 표를 넣지 않는다)."""
    make_site(client)

    phone = client.get(path, headers={"user-agent": IPHONE}).text
    web = client.get(path, headers={"user-agent": DESKTOP}).text

    assert 'class="mchips' in phone or 'class="mlist' in phone
    assert '<table class="sheet' not in phone and 'class="kpis' not in phone
    assert 'class="mlist"' not in web


def test_site_edit_menu_is_pc_only(client: TestClient) -> None:
    # 현장 수정·삭제 ··· 메뉴는 PC에서만(D-109). 앱 화면에 혼자 떠 있지 않게
    site_id = make_site(client)

    assert (
        "site-menu"
        in client.get(f"/schedule?site_id={site_id}", headers={"user-agent": DESKTOP}).text
    )
    assert (
        "site-menu"
        not in client.get(f"/schedule?site_id={site_id}", headers={"user-agent": IPHONE}).text
    )


def test_phone_judgment_week_is_a_day_picker_not_the_wide_table(
    client: TestClient, session: Session
) -> None:
    site_id = make_site(client)
    put(session, site_id, date(2026, 10, 5), time(9), time(12), "거푸집 설치")

    phone = client.get(f"/dashboard?site_id={site_id}", headers={"user-agent": IPHONE}).text
    web = client.get(f"/dashboard?site_id={site_id}", headers={"user-agent": DESKTOP}).text

    assert 'class="week week--groups"' in web
    assert 'class="mdays"' in phone and 'class="week week--groups"' not in phone
