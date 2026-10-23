"""후속 조치·검증·종료(C06, collab-contract §5).

가상 상황: 가상건설(원청) 현장의 철골 작업이 자재 지연으로 옮겨지고, 가상골조가 조치를 맡는다.
실제 현장 자료가 아니다. 현재 시각은 2026-10-04 15:00(conftest).
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.features.actions.models import ActionEvent, ActionItem
from app.features.auth.models import User
from app.features.changes.models import ChangeCase
from app.features.schedules.models import WorkItem
from app.features.teams.models import ProjectMembership
from tests.app.features.changes.test_changes import (
    OUTSIDER,
    SITE,
    SUB_USER,
    VIEWER,
    case_id_from,
    item_of,
    join,
    propose,
    revision,
)
from tests.conftest import Browser
from tests.helpers import add_site_with_work

SAFETY = {
    "email": "safety@example.com",
    "display_name": "안전 검증",
    "organization_name": "가상안전",
    "password": "safety-password-1",
}


@pytest.fixture
def item(client: TestClient, session: Session) -> WorkItem:
    add_site_with_work(client, SITE)
    return item_of(session)


def user_id(session: Session, email: str) -> int:
    found = session.scalar(select(User.id).where(User.email == email))
    assert found is not None
    return found


def participant_of(session: Session, site_id: int, email: str) -> int:
    session.expire_all()
    found = session.scalar(
        select(ProjectMembership.participant_id).where(
            ProjectMembership.site_id == site_id,
            ProjectMembership.user_id == user_id(session, email),
        )
    )
    assert found is not None
    return found


def action(session: Session, title: str = "펌프카 예약 변경") -> ActionItem:
    session.expire_all()
    return session.scalars(select(ActionItem).where(ActionItem.title == title)).one()


def add_candidate(
    client: TestClient, item: WorkItem, case_id: int, rev_id: int, **form: Any
) -> Any:
    return client.post(
        f"/changes/{case_id}/revisions/{rev_id}/actions",
        data={"site_id": item.site_id, "title": "펌프카 예약 변경", "required": "1",
              "due_date": "2026-10-05", "due_time": "17:00", **form},
        follow_redirects=False,
    )  # fmt: skip


def do(
    client: TestClient, item: WorkItem, case_id: int, a: ActionItem, kind: str, **form: Any
) -> Any:
    return client.post(
        f"/changes/{case_id}/actions/{a.id}/{kind}",
        data={"site_id": item.site_id, "revision_id": a.revision_id, **form},
        follow_redirects=False,
    )


def confirm(client: TestClient, item: WorkItem, case_id: int, rev_id: int, **form: Any) -> Any:
    return client.post(
        f"/changes/{case_id}/revisions/{rev_id}/confirm",
        data={"site_id": item.site_id, "confirm_key": f"k{rev_id}", **form},
        follow_redirects=False,
    )


@pytest.fixture
def team(client: TestClient, browser: Browser, session: Session, item: WorkItem) -> dict[str, Any]:
    """조정자(나)·안전 검증(원청 담당자)·골조 담당(협력업체 담당자)."""
    framer = join(client, browser, item.site_id, SUB_USER, "assignee")
    safety = join(client, browser, item.site_id, SAFETY, "assignee")
    return {
        "framer": framer,
        "safety": safety,
        "framer_id": user_id(session, SUB_USER["email"]),
        "safety_id": user_id(session, SAFETY["email"]),
        "framer_company": participant_of(session, item.site_id, SUB_USER["email"]),
    }


@pytest.fixture
def requested(client: TestClient, session: Session, item: WorkItem, team: dict[str, Any]) -> int:
    """골조 담당이 하고 안전 검증이 확인하는 필수 조치 하나를 요청한 변경 건."""
    case_id = case_id_from(propose(client, item))
    rev = revision(session)
    response = add_candidate(
        client, item, case_id, rev.id,
        performing_participant_id=team["framer_company"],
        assignee=f"user:{team['framer_id']}", verifier_user_id=team["safety_id"],
        done_criteria="새 예약 번호를 받음",
    )  # fmt: skip
    assert response.status_code == 303, response.text
    assert action(session).status == "candidate"
    assert confirm(client, item, case_id, rev.id).status_code == 303
    return case_id


def test_full_flow_request_accept_report_verify_then_close(
    client: TestClient, session: Session, item: WorkItem, team: dict[str, Any], requested: int
) -> None:
    a = action(session)
    assert a.status == "requested" and a.done_criteria == "새 예약 번호를 받음"
    # 필수 조치가 남아 있으면 종료할 수 없다
    blocked_close = client.post(f"/changes/{requested}/close", data={"site_id": item.site_id})
    assert blocked_close.status_code == 409 and "검증 완료되지 않았습니다" in blocked_close.text

    assert do(team["framer"], item, requested, a, "accept").status_code == 303
    report = do(team["framer"], item, requested, action(session), "report",
                body="펌프 업체와 10/6 10:00으로 변경", performed_date="2026-10-04",
                performed_time="14:30", reference="R-123")  # fmt: skip
    assert report.status_code == 303
    assert action(session).status == "reported"
    assert do(team["safety"], item, requested, action(session), "verify").status_code == 303
    assert action(session).status == "verified"

    closed = client.post(f"/changes/{requested}/close", data={"site_id": item.site_id},
                         follow_redirects=False)  # fmt: skip
    assert closed.status_code == 303
    session.expire_all()
    assert session.get(ChangeCase, requested).closed_at is not None  # type: ignore[union-attr]
    kinds = [e.kind for e in session.scalars(select(ActionEvent).order_by(ActionEvent.id))]
    assert kinds == ["requested", "accepted", "reported", "verified"]
    # 종료한 건에는 재변경을 제안할 수 없다
    again = propose(client, item_of(session), case_id=str(requested))
    assert again.status_code == 422 and "종료한 변경 건" in again.text


def test_confirm_without_required_actions_needs_a_reason(
    client: TestClient, session: Session, item: WorkItem
) -> None:
    case_id = case_id_from(propose(client, item))
    rev = revision(session)

    missing = confirm(client, item, case_id, rev.id)
    assert missing.status_code == 409 and "조치 없이 확정하는 이유" in missing.text
    assert revision(session).status == "review"  # 계획도 바뀌지 않음(같은 트랜잭션)

    ok = confirm(client, item, case_id, rev.id, no_action_reason="같은 업체 안 시간만 바뀜")
    assert ok.status_code == 303
    assert revision(session).no_action_reason == "같은 업체 안 시간만 바뀜"


def test_verifier_must_differ_from_assignee_and_reporter(
    client: TestClient, session: Session, item: WorkItem, team: dict[str, Any], requested: int
) -> None:
    # 확정으로 계획이 10/6으로 바뀌었으니 다른 날짜로 새 변경 건을 제안한다
    later = propose(client, item_of(session), title="두 번째", after_work_date="2026-10-08")
    case_id = case_id_from(later)
    same = add_candidate(
        client, item, case_id, _review_rev(session, case_id),
        performing_participant_id=team["framer_company"],
        assignee=f"user:{team['framer_id']}", verifier_user_id=team["framer_id"],
    )  # fmt: skip
    assert same.status_code == 422 and "검증자는 담당자와 다른 사람" in same.text

    # 보고한 사람(골조 담당)은 그 조치를 검증할 수 없다: 검증 버튼 자체가 검증자에게만
    a = action(session)
    do(team["framer"], item, requested, a, "accept")
    do(team["framer"], item, requested, action(session), "report", body="완료",
       performed_date="2026-10-04", performed_time="14:00")  # fmt: skip
    by_reporter = do(team["framer"], item, requested, action(session), "verify")
    assert by_reporter.status_code in (403, 409)
    assert action(session).status == "reported"


def _review_rev(session: Session, case_id: int) -> int:
    session.expire_all()
    from app.features.changes.models import ChangeRevision

    return session.scalars(select(ChangeRevision.id).where(ChangeRevision.case_id == case_id)).one()


@pytest.mark.parametrize(
    ("performed_time", "ok"), [("14:59", True), ("15:00", True), ("15:01", False)]
)
def test_report_time_cannot_be_in_the_future(
    session: Session, item: WorkItem, team: dict[str, Any], requested: int,
    performed_time: str, ok: bool,
) -> None:  # fmt: skip
    do(team["framer"], item, requested, action(session), "accept")
    response = do(team["framer"], item, requested, action(session), "report", body="완료",
                  performed_date="2026-10-04", performed_time=performed_time)  # fmt: skip
    assert (response.status_code == 303) is ok
    assert action(session).status == ("reported" if ok else "accepted")


def test_stale_revision_from_an_old_screen_is_rejected(
    session: Session, item: WorkItem, team: dict[str, Any], requested: int
) -> None:
    a = action(session)
    response = team["framer"].post(
        f"/changes/{requested}/actions/{a.id}/accept",
        data={"site_id": item.site_id, "revision_id": a.revision_id + 999},
    )
    assert response.status_code == 409 and "이전 버전의 조치" in response.text
    assert action(session).status == "requested"


def test_blocked_action_needs_reason_and_keeps_case_open(
    client: TestClient, session: Session, item: WorkItem, team: dict[str, Any], requested: int
) -> None:
    no_reason = do(team["framer"], item, requested, action(session), "block", resolver="펌프 업체")
    assert no_reason.status_code == 409 and "막힌 이유" in no_reason.text
    ok = do(team["framer"], item, requested, action(session), "block",
            body="펌프 업체 회신 없음", resolver="가상펌프 배차 담당")  # fmt: skip
    assert ok.status_code == 303 and action(session).status == "blocked"
    page = client.get(f"/changes/{requested}").text
    assert "막힌 조치 1건이 있어요." in page and "변경 건 종료</button>" not in page


def test_coordinator_records_on_behalf_of_a_roster_contact_without_account(
    client: TestClient, session: Session, item: WorkItem, team: dict[str, Any]
) -> None:
    company = team["framer_company"]
    response = client.post(
        f"/sites/{item.site_id}/participants/{company}/contacts",
        data={"contact_name": "펌프 기사", "job_title": "기사", "phone": "010-0000-0001"},
    )
    assert response.status_code == 200
    from app.features.teams.models import ParticipantContact

    contact_id = session.scalars(select(ParticipantContact.id)).one()
    case_id = case_id_from(propose(client, item))
    rev = revision(session)
    add_candidate(client, item, case_id, rev.id, performing_participant_id=company,
                  assignee=f"contact:{contact_id}", verifier_user_id=team["safety_id"])  # fmt: skip
    confirm(client, item, case_id, rev.id)
    a = action(session)
    assert a.assignee_contact_id == contact_id and a.assignee_user_id is None

    missing = do(client, item, case_id, a, "accept")
    assert missing.status_code == 409 and "연락한 상대" in missing.text
    ok = do(client, item, case_id, a, "accept", counterpart="펌프 기사 · 가상골조",
            contacted_date="2026-10-04", contacted_time="14:50")  # fmt: skip
    assert ok.status_code == 303
    event = session.scalars(select(ActionEvent).where(ActionEvent.kind == "accepted")).one()
    assert event.on_behalf and event.counterpart == "펌프 기사 · 가상골조"
    # 협력업체 담당자(계정 있음)는 명부 담당의 조치를 대신 처리하지 못한다
    assert do(team["framer"], item, case_id, action(session), "report", body="x",
              performed_date="2026-10-04", performed_time="14:00").status_code == 403  # fmt: skip


def test_viewer_cannot_act_and_outsider_gets_404(
    client: TestClient, browser: Browser, session: Session, item: WorkItem, requested: int
) -> None:
    viewer = join(client, browser, item.site_id, VIEWER, "viewer")
    outsider = browser(OUTSIDER)
    a = action(session)

    assert do(viewer, item, requested, a, "accept").status_code == 403
    assert do(outsider, item, requested, a, "accept").status_code == 404
    assert action(session).status == "requested"


def test_rechange_carries_actions_over_and_links_replacements(
    client: TestClient, session: Session, item: WorkItem, team: dict[str, Any], requested: int
) -> None:
    old = action(session)
    rev1 = old.revision_id
    # 재변경 제안: v1의 요청 대기 조치가 v2 후보로 이어진다(사람이 고치고 확정, C07)
    second = propose(client, item_of(session), case_id=str(requested), after_work_date="2026-10-07")
    assert second.status_code == 303
    rev2 = revision(session, 2)
    session.expire_all()
    carried = session.scalars(select(ActionItem).where(ActionItem.revision_id == rev2.id)).one()
    assert carried.status == "candidate" and carried.carried_from_id == old.id
    assert carried.title == old.title and carried.required

    # 이어받은 필수 후보가 있으니 이유 없이 확정된다. 이전 조치는 대체되고 새 조치로 이어진다
    assert confirm(client, item, requested, rev2.id).status_code == 303
    session.expire_all()
    replaced = session.get(ActionItem, old.id)
    assert replaced is not None and replaced.revision_id == rev1
    assert replaced.status == "replaced" and replaced.replaced_by_id == carried.id
    assert session.get(ActionItem, carried.id).status == "requested"  # type: ignore[union-attr]
    # 구버전 화면에서 늦게 누른 처리는 거부한다
    late = do(team["framer"], item, requested, replaced, "accept")
    assert late.status_code == 409 and "이전 버전의 조치" in late.text


def test_rechange_offers_a_recheck_for_already_reported_work(
    client: TestClient, session: Session, item: WorkItem, team: dict[str, Any], requested: int
) -> None:
    do(team["framer"], item, requested, action(session), "accept")
    do(team["framer"], item, requested, action(session), "report", body="예약 변경함",
       performed_date="2026-10-04", performed_time="14:00")  # fmt: skip

    propose(client, item_of(session), case_id=str(requested), after_work_date="2026-10-07")
    session.expire_all()
    recheck = session.scalars(
        select(ActionItem).where(ActionItem.revision_id == revision(session, 2).id)
    ).one()

    # 이미 보고한 일은 그대로 두고, 바뀐 일정에 맞는지 다시 확인하는 선택 후보만 제시한다
    assert recheck.title.endswith("바뀐 일정에 맞게 다시 확인") and not recheck.required
    assert recheck.due_at is None and recheck.due_note
    assert session.get(ActionItem, recheck.carried_from_id).status == "reported"  # type: ignore[union-attr]


def test_opening_the_change_records_a_view_once_without_changing_status(
    session: Session, item: WorkItem, team: dict[str, Any], requested: int
) -> None:
    team["framer"].get(f"/changes/{requested}")
    team["framer"].get(f"/changes/{requested}")
    team["safety"].get(f"/changes/{requested}")  # 검증자는 열람으로 세지 않는다

    session.expire_all()
    viewed = session.scalars(select(ActionEvent).where(ActionEvent.kind == "viewed")).all()
    assert [e.actor_user_id for e in viewed] == [team["framer_id"]]
    assert action(session).status == "requested"


def test_my_actions_groups_and_orders_overdue_first(
    client: TestClient, session: Session, item: WorkItem, team: dict[str, Any]
) -> None:
    case_id = case_id_from(propose(client, item))
    rev = revision(session)
    who = {
        "performing_participant_id": team["framer_company"],
        "assignee": f"user:{team['framer_id']}",
        "verifier_user_id": team["safety_id"],
    }
    # 일부러 화면 순서와 다르게 더한다
    add_candidate(client, item, case_id, rev.id, title="미정 일", due_date="", due_time="",
                  due_note="회신 대기", **who)  # fmt: skip
    for title, day in (
        ("먼 일", "2026-10-09"),
        ("늦은 일", "2026-10-03"),
        ("가까운 일", "2026-10-05"),
    ):
        add_candidate(client, item, case_id, rev.id, title=title, due_date=day, **who)
    confirm(client, item, case_id, rev.id)

    page = team["framer"].get("/actions").text
    respond = page.split('id="g-respond"')[1].split("</section>")[0]
    positions = [respond.index(t) for t in ("늦은 일", "가까운 일", "먼 일", "미정 일")]
    assert positions == sorted(positions)  # 기한 지남 → 가까운 기한 → 먼 기한 → 미정
    assert "기한 지남" in respond
    # 검증자에게는 보고 전 조치가 보이지 않는다
    verify_page = team["safety"].get("/actions").text
    assert "늦은 일" not in verify_page.split('id="g-respond"')[1].split("</section>")[0]


# 홈 내 차례(C04-44, D-099): 같은 조치가 맡은 사람마다 알맞은 묶음에 나온다.
def inbox(client: TestClient) -> str:
    return client.get("/").text.split('class="hsec inbox"')[1].split("</section>")[0]


def group(page: str, title: str) -> str:
    return page.split(f'<h3 class="inbox__k">{title}')[1].split("</ul>")[0]


def test_request_waits_on_the_performer_not_the_verifier(
    client: TestClient, item: WorkItem, team: dict[str, Any], requested: int
) -> None:
    framer, safety = inbox(team["framer"]), inbox(team["safety"])

    assert "펌프카 예약 변경" in group(framer, "오늘 안에")
    assert "펌프카 예약 변경" not in safety  # 검증자는 완료 보고 뒤에 본다


def test_report_moves_it_to_the_verifiers_check_list(
    client: TestClient, session: Session, item: WorkItem, team: dict[str, Any], requested: int
) -> None:
    do(team["framer"], item, requested, action(session), "accept")
    do(team["framer"], item, requested, action(session), "report",
       body="10/6 10:00으로 변경", performed_date="2026-10-04", performed_time="14:30")  # fmt: skip

    safety, framer = inbox(team["safety"]), inbox(team["framer"])

    assert "펌프카 예약 변경" in group(safety, "확인해 주세요")
    assert "펌프카 예약 변경" not in framer  # 보고한 뒤에는 협력업체 차례가 아니다


def test_coordinator_sees_blocked_work_even_when_not_assigned(
    client: TestClient, session: Session, item: WorkItem, team: dict[str, Any], requested: int
) -> None:
    do(team["framer"], item, requested, action(session), "block",
       body="펌프 업체 회신 없음", resolver="가상펌프 배차 담당")  # fmt: skip

    mine = inbox(client)

    assert "펌프카 예약 변경" in group(mine, "막힌 일")
    assert mine.count("펌프카 예약 변경") == 1  # 같은 조치를 두 번 넣지 않는다
    flow = client.get("/").text.split('class="flow"')[1].split("</a>")[0]
    assert "<b>1</b><small>막힘</small>" in flow
