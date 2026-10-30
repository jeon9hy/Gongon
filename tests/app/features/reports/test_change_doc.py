"""변경 건 문서(C14-4, D-112). 가상 현장·가상 계정만 쓴다. 현재 시각은 2026-10-04(일) 15:00."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.features.schedules.models import WorkItem
from tests.app.features.actions.test_actions import item, requested, team
from tests.app.features.changes.test_changes import OUTSIDER, VIEWER, case_id_from, join, propose
from tests.conftest import Browser

__all__ = ["item", "requested", "team"]


def doc(client: TestClient, site_id: int, case_id: int, kind: str = "order") -> Any:
    return client.get(f"/reports/{site_id}/changes/{case_id}?kind={kind}")


def test_work_order_lists_each_company_action_with_a_sign_box(
    client: TestClient, item: WorkItem, team: dict[str, Any], requested: int
) -> None:
    page = doc(client, item.site_id, requested).text
    assert "변경 통보 · 작업 지시서" in page and "펌프카 예약 변경" in page
    assert "가상골조" in page and "새 예약 번호를 받음" in page and "안전 검증" in page
    assert "확인(협력업체)" in page and "아직 확정 전" not in page
    assert "[가상] 자재 반입 지연" in page and "10/06(화) 10:00-13:00" in page
    # 모르는 종류는 작업 지시서로
    assert "변경 통보 · 작업 지시서" in doc(client, item.site_id, requested, "x").text


def test_site_report_draft_has_history_and_results(
    client: TestClient, item: WorkItem, team: dict[str, Any], requested: int
) -> None:
    page = doc(client, item.site_id, requested, "report").text
    assert "실정보고 초안" in page and "3. 변경 이력" in page and "4. 검토 의견" in page
    assert "요청 대기" in page and "확인(협력업체)" not in page


def test_unconfirmed_change_is_marked_as_such(
    client: TestClient, session: Session, item: WorkItem
) -> None:
    case_id = case_id_from(propose(client, item))
    page = doc(client, item.site_id, case_id).text
    assert "아직 확정 전" in page and "등록된 조치가 없어요" in page


def test_case_must_belong_to_the_site_in_the_address(
    client: TestClient, browser: Browser, item: WorkItem, requested: int
) -> None:
    assert doc(client, item.site_id + 999, requested).status_code == 404
    assert doc(browser(OUTSIDER), item.site_id, requested).status_code == 404
    viewer = join(client, browser, item.site_id, VIEWER, "viewer")
    assert doc(viewer, item.site_id, requested).status_code == 200
