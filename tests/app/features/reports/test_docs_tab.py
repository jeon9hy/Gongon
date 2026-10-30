"""서류 탭(D-116). 가상 현장·가상 계정만 쓴다. 현재 시각은 2026-10-04(일) 15:00."""

from typing import Any

from fastapi.testclient import TestClient

from app.features.schedules.models import WorkItem
from tests.app.features.changes.test_changes import OUTSIDER, SITE
from tests.app.features.reports.test_daily import item, record, team, today_work
from tests.conftest import Browser
from tests.helpers import add_site_with_work

__all__ = ["item", "team", "today_work"]


def test_docs_is_a_main_tab_and_the_site_menu_no_longer_lists_documents(
    client: TestClient, item: WorkItem
) -> None:
    home = client.get("/home").text
    assert 'href="/reports" data-site-link="docs"' in home
    schedule = client.get(f"/schedule?site_id={item.site_id}").text
    assert f"/reports/{item.site_id}/daily" not in schedule  # 현장 ··· 메뉴에서 뺐다
    daily = client.get(f"/reports/{item.site_id}/daily").text
    assert 'aria-label="서류 메뉴"' in daily and f'href="/reports/{item.site_id}/weekly"' in daily


def test_picked_site_goes_straight_to_its_document(client: TestClient, item: WorkItem) -> None:
    to_weekly = client.get(f"/reports?site_id={item.site_id}&tab=weekly", follow_redirects=False)
    assert to_weekly.headers["location"] == f"/reports/{item.site_id}/weekly"
    odd = client.get(f"/reports?site_id={item.site_id}&tab=xx", follow_redirects=False)
    assert odd.headers["location"] == f"/reports/{item.site_id}/daily"


def test_all_sites_list_only_my_sites_with_todays_report_count(
    client: TestClient, browser: Browser, today_work: WorkItem, team: dict[str, Any]
) -> None:
    other = browser(OUTSIDER)
    add_site_with_work(other, {**SITE, "name": "남의현장"})

    page = client.get("/reports").text
    assert "가상A현장" in page and "남의현장" not in page
    assert "오늘 일보 0/1건" in page and "1건 남음" in page
    record(client, today_work)
    assert "오늘 일보 1/1건" in client.get("/reports").text
