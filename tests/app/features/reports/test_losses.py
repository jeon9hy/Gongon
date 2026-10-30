"""작업 차질 월 집계(C14-5, D-113). 가상 현장·가상 계정만 쓴다.

현재 시각은 2026-10-04(일) 15:00.
"""

import re
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.features.schedules.models import WorkItem
from tests.app.features.changes.test_changes import OUTSIDER
from tests.app.features.reports.test_daily import item, record, team, today_work, work_on
from tests.conftest import Browser

__all__ = ["item", "team", "today_work"]


def summary(client: TestClient, site_id: int, month: str = "") -> str:
    page = client.get(f"/reports/{site_id}/losses" + (f"?month={month}" if month else ""))
    assert page.status_code == 200, page.text
    return page.text


def row(page: str, label: str) -> list[str]:
    found = re.search(rf"<tr><th scope=\"row\">{label}</th>(.*?)</tr>", page)
    assert found is not None, label
    return re.findall(r"<td>(.*?)</td>", found.group(1))


def test_multi_cause_records_count_per_cause_but_once_in_the_total(
    client: TestClient, session: Session, item: WorkItem, today_work: WorkItem,
    team: dict[str, Any],
) -> None:  # fmt: skip
    other = work_on(client, session, item.site_id, "2026-10-04", "16:30", "18:00",
                    team["safety_company"])  # fmt: skip
    third = work_on(client, session, item.site_id, "2026-10-04", "17:00", "18:00",
                    team["framer_company"])  # fmt: skip
    record(client, today_work, outcome="partial", causes=["material", "schedule"], workers="6",
           known_when="morning")  # fmt: skip
    record(client, other, outcome="not_done", causes="material", known_when="day_before")
    record(client, third, workers="4")  # 했음은 세지 않는다

    page = summary(client, item.site_id)

    # 열: 일부만 · 못함 · 인원 · 전날 · 당일 아침 · 현장 와서 · 모름
    assert row(page, "자재") == ["1", "1", "6", "1", "1", "0", "0"]
    assert row(page, "공정·선행 작업") == ["1", "0", "6", "0", "1", "0", "0"]
    assert row(page, "합계") == ["1", "1", "6", "1", "1", "0", "0"]
    assert "작업일보</dt><dd>3건" in page
    assert page.index('<th scope="row">자재') < page.index('<th scope="row">공정·선행')  # 많은 순


def test_unknown_workers_stay_blank_and_other_months_are_empty(
    client: TestClient, browser: Browser, today_work: WorkItem
) -> None:
    record(client, today_work, outcome="not_done", causes="equipment")
    page = summary(client, today_work.site_id)
    assert row(page, "장비") == ["0", "1", "-", "0", "0", "0", "1"]  # 인원 모름 · 언제 모름
    assert "일부만·못함으로 남긴 작업이 없어요" in summary(client, today_work.site_id, "2026-11")
    assert browser(OUTSIDER).get(f"/reports/{today_work.site_id}/losses").status_code == 404
