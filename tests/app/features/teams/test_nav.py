"""주 메뉴 5탭과 현장 고르기(C04-33·C04-35·C04-36, D-090~D-092).

현장 고르기는 머리줄 칩 하나다(대화 빼고 모든 화면, 전체 포함). 서버가 그리는 탭 주소는 전체이고,
칩에서 고른 값은 브라우저 쿠키로 다른 탭에도 이어진다(스크립트, 여기서는 서버 쪽만 검사).
업체 탭의 전체 보기는 현장별 업체를 한 표에 모은다(엑셀처럼). 대화는 방을 미리 고르지 않는다.
참여하지 않은 현장은 고를 수도, 표에 보일 수도 없다.
"""

import re

from fastapi.testclient import TestClient

from tests.app.features.teams.test_roster import add_site, register
from tests.conftest import Browser

OTHER = {
    "email": "other@example.com",
    "display_name": "다른 사람",
    "organization_name": "가상다른건설",
    "password": "other-password-1",
}


def nav_of(page: str) -> str:
    return page.split('<nav class="appnav"')[1].split("</nav>")[0]


def test_team_tab_opens_all_sites_in_one_table_and_a_chosen_site_opens_its_page(
    client: TestClient,
) -> None:
    first = add_site(client, "가상A현장")
    second = add_site(client, "가상B현장")
    register(client, first, "가상펌프")
    register(client, second, "가상골조")

    all_sites = client.get("/team")
    chosen = client.get(f"/team?site_id={second}", follow_redirects=False)

    assert all_sites.status_code == 200
    tables = all_sites.text.split('<table class="sheet sheet--fixed">')[1:]
    # 현장마다 제목 한 줄 + 표 하나(원청·추가 업체 두 줄). 현장 이름은 줄에 반복하지 않는다
    assert len(tables) == 2 and all(t.split("</table>")[0].count("<tr") == 1 + 2 for t in tables)
    assert all_sites.text.count('class="sheet-site"') == 2
    assert "가상펌프" in tables[0] + tables[1] and "가상골조" in tables[0] + tables[1]
    assert '<a class="sheet__clip"' not in all_sites.text  # 업체 이름은 링크가 아니다
    assert 'data-site-link="team" aria-current="page"' in nav_of(all_sites.text)
    assert chosen.status_code == 303 and chosen.headers["location"] == f"/sites/{second}/members"


def test_team_table_never_shows_a_site_the_user_does_not_join(
    client: TestClient, browser: Browser
) -> None:
    add_site(client, "가상A현장")
    other = browser(OTHER)
    theirs = add_site(other, "남의현장")
    register(other, theirs, "남의업체")

    response = client.get(f"/team?site_id={theirs}", follow_redirects=False)

    assert response.status_code == 200  # 고를 수 없는 현장이면 전체 표
    assert "남의현장" not in response.text and "남의업체" not in response.text


def test_team_tab_without_any_site_goes_to_site_setup(client: TestClient) -> None:
    response = client.get("/team", follow_redirects=False)

    assert response.headers["location"] == "/sites"


def test_site_member_page_is_one_table_with_people_in_the_company_dialog(
    client: TestClient,
) -> None:
    site_id = add_site(client, "가상A현장")
    add_site(client, "가상B현장")
    register(client, site_id, "가상펌프", trade_note="펌프카")

    page = client.get(f"/sites/{site_id}/members").text

    assert page.count('<table class="sheet') == 1  # 담당자는 따로 표를 두지 않는다
    pump = page.split(">가상펌프<")[1].split("</tr>")[0]
    assert "업체 정보" in pump and "dlg-info-" in pump  # 줄에는 업체 정보만, 수정은 관리 메뉴로
    assert 'data-sheet-edit="company-sheet"' in page and 'data-tab-btn="people"' in page
    assert 'id="team-site"' not in page  # 화면 안 드롭다운 없이 머리줄 칩 하나
    assert "data-siteswitch-label>가상A현장<" in page


def test_switcher_lists_only_joined_sites_with_add_and_settings(
    client: TestClient, browser: Browser
) -> None:
    add_site(client, "가상A현장")
    other = browser(OTHER)
    add_site(other, "남의현장")

    html = client.get("/sites/switcher").text

    assert "가상A현장" in html and "남의현장" not in html
    assert "현장 추가" in html and "현장 설정" in html and "전체 현장" in html
    # 톱니는 페이지 이동이 아니라 설정 모달(C04-57)
    assert 'data-site-dialog="/sites?embed=1&amp;pick=1"' in html


def test_settings_modal_from_all_sites_lists_only_joined_sites_to_pick(
    client: TestClient, browser: Browser
) -> None:
    add_site(client, "가상A현장")
    add_site(browser(OTHER), "남의현장")

    picker = client.get("/sites?embed=1&pick=1").text

    assert "가상A현장" in picker and "남의현장" not in picker
    assert "&amp;embed=1" in picker  # 고르면 같은 모달 안에서 그 현장 설정을 연다
    assert 'class="appbar' not in picker  # 모달 안 화면이라 앱 메뉴가 없다


def test_changes_and_actions_share_a_sub_menu_and_me_has_no_work_cards(
    client: TestClient,
) -> None:
    add_site(client)
    for path, current in (("/changes", "변경 건"), ("/actions", "내 조치")):
        page = client.get(path).text
        subnav = page.split('<nav class="subnav" aria-label="변경·조치 메뉴">')[1]
        assert f'aria-current="page">{current}</a>' in subnav.split("</nav>")[0]
        assert 'data-site-link="changes" aria-current="page"' in nav_of(page)
        assert "data-siteswitch-label>전체 현장<" in page  # 칩 하나로 고른다
    assert 'id="changes-site"' not in client.get("/changes").text
    assert "profile-link" not in client.get("/me").text


def test_every_tab_has_the_chip_except_chat_and_chat_opens_no_room(client: TestClient) -> None:
    first = add_site(client, "가상A현장")
    add_site(client, "가상B현장")
    nav = nav_of(client.get(f"/schedule?site_id={first}").text)
    for key, href in (("home", "/"), ("schedule", "/schedule"), ("changes", "/changes"),
                      ("team", "/team"), ("chat", "/chat")):  # fmt: skip
        assert f'href="{href}" data-site-link="{key}"' in nav  # 서버 주소는 전체

    home = client.get("/").text
    dashboard = client.get(f"/dashboard?site_id={first}").text
    team = client.get("/team").text
    chat = client.get("/chat", follow_redirects=False)

    assert "data-siteswitch-label>전체 현장<" in home and "data-siteswitch-label>전체 현장<" in team
    assert "data-siteswitch-label>가상A현장<" in dashboard
    assert 'class="sitetabs"' not in home and 'id="site-select"' not in dashboard
    # 대화는 칩이 없고, 방을 고르지 않으면 방 목록만 있는 빈 화면(처음 방을 열지 않는다)
    assert chat.status_code == 200
    assert '<details class="siteswitch"' not in chat.text
    assert "대화할 현장 방을 골라 주세요." in chat.text
    assert f'href="/chat/{first}"' in chat.text and 'id="chat-title"' not in chat.text


def test_my_actions_follow_the_chip_and_ignore_a_site_not_joined(
    client: TestClient, browser: Browser
) -> None:
    mine = add_site(client, "가상A현장")
    add_site(client, "가상B현장")
    theirs = add_site(browser(OTHER), "남의현장")

    chosen = client.get(f"/actions?site_id={mine}").text
    foreign = client.get(f"/actions?site_id={theirs}").text

    assert "data-siteswitch-label>가상A현장<" in chosen
    assert "data-siteswitch-label>전체 현장<" in foreign and "남의현장" not in foreign


def test_only_site_keeps_that_sites_actions_in_every_group() -> None:
    from app.features.actions.schemas import MyActionItem, MyActionsView
    from app.features.actions.service import only_site

    def item(site_id: int) -> MyActionItem:
        return MyActionItem("/x", f"조치 {site_id}", "", "요청", "", False, "처리", site_id)

    view = MyActionsView(
        to_respond=(item(1), item(2)), blocked=(item(2),), to_verify=(item(1),),
        delegations=(), delegate_choices=(),
    )  # fmt: skip

    filtered = only_site(view, 1, "가상A현장")

    assert [i.site_id for i in filtered.to_respond] == [1]
    assert filtered.blocked == () and [i.site_id for i in filtered.to_verify] == [1]
    assert (filtered.site_id, filtered.site_name) == (1, "가상A현장")


def test_people_count_includes_the_logged_in_founder(client: TestClient) -> None:
    # 담당자 수는 명부 담당자와 로그인 참여자를 합친다. 만든 사람(원청 조정자)은 1부터
    site_id = add_site(client, "가상A현장")

    page = client.get(f"/sites/{site_id}/members").text
    prime = page.split("</tr>")[1]  # 머리줄 다음 첫 줄이 원청

    assert re.findall(r'<td class="sheet__num">(\d+)</td>', prime) == ["1"]  # 담당자 수
