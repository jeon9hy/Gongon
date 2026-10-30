"""형식 때문에 늘던 입력 줄이기(D-114). 가상 현장·가상 계정만 쓴다.

현재 시각은 2026-10-04(일) 15:00(conftest).
"""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.features.changes.models import ChangeCase
from app.features.schedules.models import WorkItem
from tests.app.features.actions.test_actions import (
    action,
    add_candidate,
    confirm,
    do,
    item,
    requested,
    team,
    user_id,
)
from tests.app.features.changes.test_changes import case_id_from, propose, revision
from tests.conftest import FIXED_NOW

__all__ = ["item", "requested", "team"]


def closed(session: Session, case_id: int) -> bool:
    session.expire_all()
    return session.get(ChangeCase, case_id).closed_at is not None  # type: ignore[union-attr]


def test_report_without_accepting_first_and_blank_time_means_now(
    session: Session, item: WorkItem, team: dict[str, Any], requested: int
) -> None:
    assert action(session).status == "requested"
    report = do(team["framer"], item, requested, action(session), "report", body="예약 변경함")
    assert report.status_code == 303
    a = action(session)
    assert a.status == "reported" and a.performed_at == FIXED_NOW
    # 날짜만 적고 시각을 비우면 어느 때인지 몰라 거부한다
    assert do(team["safety"], item, requested, a, "reject", body="번호 없음").status_code == 303
    half = do(team["framer"], item, requested, action(session), "report", body="다시",
              performed_date="2026-10-04")  # fmt: skip
    assert half.status_code == 409 and "함께 입력" in half.text


def test_block_needs_only_a_reason(
    session: Session, item: WorkItem, team: dict[str, Any], requested: int
) -> None:
    ok = do(team["framer"], item, requested, action(session), "block", body="펌프 회신 없음")
    assert ok.status_code == 303
    a = action(session)
    assert a.status == "blocked" and a.blocked_resolver is None


def test_due_can_stay_open_without_a_reason(
    client: TestClient, session: Session, item: WorkItem, team: dict[str, Any]
) -> None:
    case_id = case_id_from(propose(client, item))
    rev = revision(session)
    response = add_candidate(
        client, item, case_id, rev.id, due_date="", due_time="",
        performing_participant_id=team["framer_company"],
        assignee=f"user:{team['framer_id']}", verifier_user_id=team["safety_id"],
    )  # fmt: skip
    assert response.status_code == 303, response.text
    a = action(session)
    assert a.due_at is None and a.due_note is None
    assert "기한 미정" in client.get(f"/changes/{case_id}").text


def test_verifier_defaults_to_the_person_adding_the_action(
    client: TestClient, session: Session, item: WorkItem, team: dict[str, Any]
) -> None:
    case_id = case_id_from(propose(client, item))
    page = client.get(f"/changes/{case_id}").text
    verifier_select = page.split('name="verifier_user_id"')[1].split("</select>")[0]
    me = user_id(session, "coordinator@example.com")
    assert f'<option value="{me}" selected>테스트 조정자' in verifier_select


def test_auto_close_waits_for_optional_actions_too(
    client: TestClient, session: Session, item: WorkItem, team: dict[str, Any]
) -> None:
    case_id = case_id_from(propose(client, item))
    rev = revision(session)
    common = {
        "performing_participant_id": team["framer_company"],
        "assignee": f"user:{team['framer_id']}",
        "verifier_user_id": team["safety_id"],
    }
    add_candidate(client, item, case_id, rev.id, **common)
    add_candidate(client, item, case_id, rev.id, title="안전 교육 다시", required="", **common)
    assert confirm(client, item, case_id, rev.id).status_code == 303

    must = action(session)
    assert do(team["framer"], item, case_id, must, "report", body="완료").status_code == 303
    assert do(team["safety"], item, case_id, action(session), "verify").status_code == 303
    assert not closed(session, case_id)  # 선택 조치가 아직 남음

    optional = action(session, "안전 교육 다시")
    assert do(client, item, case_id, optional, "exclude", body="필요 없어짐").status_code == 303
    assert closed(session, case_id)
