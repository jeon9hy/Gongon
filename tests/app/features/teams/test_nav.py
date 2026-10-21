"""주 메뉴 5탭과 현장 고르기 칩(C04-33 안 A, D-090).

업체 탭(/team)은 고른 현장의 참여 업체 화면으로 보내고, 참여하지 않은 현장은 고를 수 없다.
현장 고르기 칩의 목록은 참여한 현장만 보인다.
"""

from fastapi.testclient import TestClient

from tests.app.features.teams.test_roster import add_site
from tests.conftest import Browser

OTHER = {
    "email": "other@example.com",
    "display_name": "다른 사람",
    "organization_name": "가상다른건설",
    "password": "other-password-1",
}


def test_team_tab_opens_the_chosen_or_first_site_members(client: TestClient) -> None:
    first = add_site(client, "가상A현장")
    second = add_site(client, "가상B현장")

    chosen = client.get(f"/team?site_id={second}", follow_redirects=False)
    fallback = client.get("/team", follow_redirects=False)

    assert chosen.status_code == 303 and chosen.headers["location"] == f"/sites/{second}/members"
    assert fallback.headers["location"] in (f"/sites/{first}/members", f"/sites/{second}/members")
    page = client.get(f"/sites/{second}/members").text
    nav = page.split('<nav class="appnav"')[1].split("</nav>")[0]
    assert 'data-site-link="team" aria-current="page"' in nav


def test_team_tab_ignores_a_site_the_user_does_not_join(
    client: TestClient, browser: Browser
) -> None:
    mine = add_site(client, "가상A현장")
    other = browser(OTHER)
    theirs = add_site(other, "남의현장")

    response = client.get(f"/team?site_id={theirs}", follow_redirects=False)

    assert response.headers["location"] == f"/sites/{mine}/members"


def test_team_tab_without_any_site_goes_to_site_setup(client: TestClient) -> None:
    response = client.get("/team", follow_redirects=False)

    assert response.headers["location"] == "/sites"


def test_switcher_lists_only_joined_sites_with_add_and_settings(
    client: TestClient, browser: Browser
) -> None:
    add_site(client, "가상A현장")
    other = browser(OTHER)
    add_site(other, "남의현장")

    html = client.get("/sites/switcher").text

    assert "가상A현장" in html and "남의현장" not in html
    assert "현장 추가" in html and "현장 설정" in html


def test_changes_and_actions_share_a_sub_menu_and_me_has_no_work_cards(
    client: TestClient,
) -> None:
    add_site(client)
    for path, current in (("/changes", "변경 건"), ("/actions", "내 조치")):
        page = client.get(path).text
        subnav = page.split('<nav class="subnav" aria-label="변경·조치 메뉴">')[1].split("</nav>")[
            0
        ]
        assert f'aria-current="page">{current}</a>' in subnav
        nav = page.split('<nav class="appnav"')[1].split("</nav>")[0]
        assert 'data-site-link="changes" aria-current="page"' in nav
    assert "profile-link" not in client.get("/me").text
