"""변경 건·버전·확정(C05, collab-contract §4).

C01 합성 시나리오를 줄인 가상 상황: 가상건설(원청) 현장의 내일 철골 작업을 다른 날로 옮긴다.
실제 현장 자료가 아니다.
"""

import re
from datetime import date, time
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.features.changes import service as changes_service
from app.features.changes.models import ChangeCase, ChangeRevision
from app.features.judgments import service as judgments_service
from app.features.schedules.models import WorkItem, WorkItemRevision
from tests.conftest import FIXED_NOW, Browser
from tests.helpers import add_site_with_work

SITE: dict[str, Any] = {
    "name": "가상A현장",
    "road_address": "서울 중구 세종대로 110",
    "latitude": "37.5665",
    "longitude": "126.9780",
    "work_start_date": "2026-10-01",
    "work_end_date": "2026-12-31",
    "work_types": ["철골 작업"],
    "work_start": "09:00",
    "work_end": "12:00",
}
SUB_USER = {
    "email": "framer@example.com",
    "display_name": "골조 담당",
    "organization_name": "가상골조",
    "password": "framer-password-1",
}
VIEWER = {
    "email": "viewer@example.com",
    "display_name": "열람만",
    "organization_name": "가상감리",
    "password": "viewer-password-1",
}
OUTSIDER = {
    "email": "outsider@example.com",
    "display_name": "무관한 사람",
    "organization_name": "무관건설",
    "password": "outsider-password",
}


def item_of(session: Session) -> WorkItem:
    session.expire_all()
    return session.scalars(select(WorkItem)).one()


def proposal(item: WorkItem, **changes: Any) -> dict[str, Any]:
    return {
        "site_id": item.site_id,
        "work_item_id": item.id,
        "title": "철골 작업 연기",
        "after_work_date": "2026-10-06",
        "after_start": "10:00",
        "after_end": "13:00",
        "after_location": "A구역",
        "reasons": ["material"],
        "basis_note": "[가상] 자재 반입 지연",
        "plan_version": item.plan_version,
        "submit": "review",
        **changes,
    }


def propose(client: TestClient, item: WorkItem, **changes: Any) -> Any:
    return client.post("/changes", data=proposal(item, **changes), follow_redirects=False)


def case_id_from(response: Any) -> int:
    assert response.status_code == 303, response.text
    return int(re.search(r"/changes/(\d+)", response.headers["location"]).group(1))  # type: ignore[union-attr]


def revision(session: Session, number: int = 1) -> ChangeRevision:
    session.expire_all()
    return session.scalars(select(ChangeRevision).where(ChangeRevision.number == number)).one()


def confirm(client: TestClient, item: WorkItem, case_id: int, rev_id: int, key: str = "k1") -> Any:
    return client.post(
        f"/changes/{case_id}/revisions/{rev_id}/confirm",
        data={"site_id": item.site_id, "confirm_key": key},
        follow_redirects=False,
    )


def join(client: TestClient, browser: Browser, site_id: int, user: dict[str, str], role: str
         ) -> TestClient:  # fmt: skip
    other = browser(user)
    response = client.post(f"/sites/{site_id}/members", data={"email": user["email"], "role": role})
    assert response.status_code == 200
    return other


@pytest.fixture
def item(client: TestClient, session: Session) -> WorkItem:
    add_site_with_work(client, SITE)
    return item_of(session)


def test_confirming_a_reviewed_change_updates_the_plan_once(
    client: TestClient, session: Session, item: WorkItem
) -> None:
    case_id = case_id_from(propose(client, item))
    rev = revision(session)
    assert rev.status == "review" and rev.based_on_plan_version == 1
    assert (rev.before_work_date, rev.before_start_local) == (date(2026, 10, 5), time(9, 0))

    response = confirm(client, item, case_id, rev.id)

    assert "done=confirmed" in response.headers["location"]
    moved = item_of(session)
    assert (moved.work_date, moved.start_local, moved.end_local, moved.plan_version) == (
        date(2026, 10, 6), time(10, 0), time(13, 0), 2
    )  # fmt: skip
    saved = session.scalars(select(WorkItemRevision)).one()
    assert (saved.source, saved.plan_version, saved.work_date) == ("change", 1, date(2026, 10, 5))
    rev = revision(session)
    assert rev.status == "confirmed" and rev.confirmed_at == FIXED_NOW
    page = client.get(f"/changes/{case_id}").text
    assert "현재 확정 v1" in page and "공급사 예약·출역 변경이 끝났다는 뜻이 아닙니다" in page


def test_resending_the_same_confirm_does_not_apply_twice(
    client: TestClient, session: Session, item: WorkItem
) -> None:
    case_id = case_id_from(propose(client, item))
    rev_id = revision(session).id

    first = confirm(client, item, case_id, rev_id, key="same")
    again = confirm(client, item, case_id, rev_id, key="same")
    other_key = confirm(client, item, case_id, rev_id, key="different")

    assert "done=confirmed" in first.headers["location"]
    assert "done=already" in again.headers["location"]
    assert other_key.status_code == 409 and "확정 상태라 확정할 수 없습니다" in other_key.text
    assert item_of(session).plan_version == 2
    assert len(session.scalars(select(WorkItemRevision)).all()) == 1


def test_plan_changed_after_proposal_blocks_confirmation(
    client: TestClient, session: Session, item: WorkItem
) -> None:
    case_id = case_id_from(propose(client, item))
    rev_id = revision(session).id
    # 제안 뒤 작업 일정 화면에서 계획이 바뀐 상황
    edit = {"site_id": item.site_id, "day": "2026-10-05", "work_date": "2026-10-05",
            "start": "08:00", "end": "12:00", "plan_version": "1"}  # fmt: skip
    assert client.post(f"/schedule/{item.id}/edit", data=edit).status_code == 200

    response = confirm(client, item, case_id, rev_id)

    assert response.status_code == 409 and "제안 뒤 작업 계획이 바뀌어" in response.text
    current = item_of(session)
    assert (current.start_local, current.plan_version) == (time(8, 0), 2)
    assert revision(session).status == "review"


def test_failure_inside_confirmation_rolls_everything_back(
    client: TestClient, session: Session, item: WorkItem, monkeypatch: pytest.MonkeyPatch
) -> None:
    case_id = case_id_from(propose(client, item))
    rev_id = revision(session).id

    def broken(*_: Any) -> None:
        raise RuntimeError("조치 생성 실패를 흉내 냄")

    monkeypatch.setattr(changes_service, "_after_confirm", broken)
    with pytest.raises(RuntimeError):
        confirm(client, item, case_id, rev_id)

    current = item_of(session)
    assert (current.work_date, current.plan_version) == (date(2026, 10, 5), 1)
    assert session.scalar(select(WorkItemRevision.id)) is None
    assert revision(session).status == "review"


def test_proposal_from_an_outdated_screen_is_refused(
    client: TestClient, session: Session, item: WorkItem
) -> None:
    response = propose(client, item, plan_version=0)

    assert response.status_code == 422 and "작업 계획이 바뀌었습니다" in response.text
    assert session.scalar(select(ChangeCase.id)) is None


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"reasons": []}, "변경 원인을 하나 이상"),
        ({"reasons": ["material", "magic"]}, "목록에 있는 변경 원인"),
        ({"title": " "}, "변경 제목"),
        ({"after_work_date": "2026-10-03"}, "오늘 이후"),
        ({"after_work_date": "2027-01-04"}, "작업 기간"),
        ({"after_start": "13:00", "after_end": "13:00"}, "종료는 시작보다"),
        ({"after_work_date": "2026-10-05", "after_start": "09:00", "after_end": "12:00",
          "after_location": ""}, "바뀐 내용이 없습니다"),
    ],
)  # fmt: skip
def test_invalid_proposals_save_nothing(
    client: TestClient, session: Session, item: WorkItem, changes: dict[str, Any], message: str
) -> None:
    response = propose(client, item, **changes)

    assert response.status_code == 422 and message in response.text
    assert session.scalar(select(ChangeRevision.id)) is None


def test_today_is_allowed_for_an_urgent_change(
    client: TestClient, session: Session, item: WorkItem
) -> None:
    assert propose(client, item, after_work_date="2026-10-04").status_code == 303


def test_only_one_open_proposal_per_case(
    client: TestClient, session: Session, item: WorkItem
) -> None:
    case_id = case_id_from(propose(client, item))

    second = propose(client, item, case_id=case_id, after_start="11:00", after_end="14:00")

    assert second.status_code == 422 and "진행 중인 제안이 있습니다" in second.text
    assert len(session.scalars(select(ChangeRevision)).all()) == 1


def test_rechange_supersedes_the_previous_confirmed_version(
    client: TestClient, session: Session, item: WorkItem
) -> None:
    case_id = case_id_from(propose(client, item))
    confirm(client, item, case_id, revision(session).id, key="v1")
    moved = item_of(session)

    again = propose(client, moved, case_id=case_id, after_work_date="2026-10-07",
                    reasons=["weather", "labor"])  # fmt: skip
    assert again.status_code == 303
    v2 = revision(session, 2)
    assert (v2.before_work_date, v2.based_on_plan_version) == (date(2026, 10, 6), 2)
    confirm(client, moved, case_id, v2.id, key="v2")

    assert [revision(session, 1).status, revision(session, 2).status] == ["superseded", "confirmed"]
    assert revision(session, 1).superseded_at == FIXED_NOW
    assert (item_of(session).work_date, item_of(session).plan_version) == (date(2026, 10, 7), 3)
    page = client.get(f"/changes/{case_id}").text
    assert "현재 확정 v2" in page and "대체됨" in page


def test_withdrawal_needs_a_reason_and_confirmed_versions_cannot_be_withdrawn(
    client: TestClient, session: Session, item: WorkItem
) -> None:
    case_id = case_id_from(propose(client, item))
    rev_id = revision(session).id
    url = f"/changes/{case_id}/revisions/{rev_id}/withdraw"

    empty = client.post(url, data={"site_id": item.site_id, "reason": " "})
    done = client.post(url, data={"site_id": item.site_id, "reason": "[가상] 자재 도착"},
                       follow_redirects=False)  # fmt: skip
    after = confirm(client, item, case_id, rev_id)

    assert empty.status_code == 409 and "철회 이유" in empty.text
    assert "done=withdrawn" in done.headers["location"]
    assert after.status_code == 409 and item_of(session).plan_version == 1

    # 확정한 버전은 철회 대상이 아니다
    new_case = case_id_from(propose(client, item, title="다른 변경"))
    new_rev = session.scalars(
        select(ChangeRevision).where(ChangeRevision.case_id == new_case)
    ).one()
    confirm(client, item, new_case, new_rev.id, key="x")
    refused = client.post(f"/changes/{new_case}/revisions/{new_rev.id}/withdraw",
                          data={"site_id": item.site_id, "reason": "취소"})  # fmt: skip
    assert refused.status_code == 409 and "재변경을 제안하세요" in refused.text


def test_assignee_proposes_but_only_coordinator_confirms(
    client: TestClient, browser: Browser, session: Session, item: WorkItem
) -> None:
    framer = join(client, browser, item.site_id, SUB_USER, "assignee")

    case_id = case_id_from(framer.post("/changes", data=proposal(item, submit="draft"),
                                       follow_redirects=False))  # fmt: skip
    rev_id = revision(session).id
    submitted = framer.post(f"/changes/{case_id}/revisions/{rev_id}/submit",
                            data={"site_id": item.site_id}, follow_redirects=False)  # fmt: skip
    refused = confirm(framer, item, case_id, rev_id)

    assert "done=submitted" in submitted.headers["location"]
    assert refused.status_code == 403
    assert item_of(session).plan_version == 1
    assert "확정 · 작업 계획 바꾸기" not in framer.get(f"/changes/{case_id}").text
    assert "확정 · 작업 계획 바꾸기" in client.get(f"/changes/{case_id}").text


def test_assignee_cannot_withdraw_someone_elses_proposal(
    client: TestClient, browser: Browser, session: Session, item: WorkItem
) -> None:
    framer = join(client, browser, item.site_id, SUB_USER, "assignee")
    case_id = case_id_from(propose(client, item))
    rev_id = revision(session).id

    response = framer.post(f"/changes/{case_id}/revisions/{rev_id}/withdraw",
                           data={"site_id": item.site_id, "reason": "싫음"})  # fmt: skip

    assert response.status_code == 403 and revision(session).status == "review"


def test_viewer_can_read_but_not_propose(
    client: TestClient, browser: Browser, session: Session, item: WorkItem
) -> None:
    viewer = join(client, browser, item.site_id, VIEWER, "viewer")
    case_id = case_id_from(propose(client, item))

    assert viewer.get(f"/changes/{case_id}").status_code == 200
    assert viewer.get(f"/changes/new?site_id={item.site_id}&item_id={item.id}").status_code == 403
    assert viewer.post("/changes", data=proposal(item)).status_code == 403
    assert "변경 제안" not in viewer.get(f"/schedule?site_id={item.site_id}&day=2026-10-05").text


def test_outsider_sees_nothing_and_cannot_act(
    client: TestClient, browser: Browser, session: Session, item: WorkItem
) -> None:
    outsider = browser(OUTSIDER)
    case_id = case_id_from(propose(client, item))
    rev_id = revision(session).id

    assert outsider.get(f"/changes/{case_id}").status_code == 404
    assert outsider.get(f"/changes?site_id={item.site_id}").status_code == 404
    assert "철골 작업 연기" not in outsider.get("/changes").text
    assert confirm(outsider, item, case_id, rev_id).status_code == 404
    assert item_of(session).plan_version == 1


def test_revision_of_another_sites_case_is_not_reachable(
    client: TestClient, browser: Browser, session: Session, item: WorkItem
) -> None:
    outsider = browser(OUTSIDER)
    other_site = add_site_with_work(outsider, {**SITE, "name": "무관현장"})
    other_item = session.scalars(select(WorkItem).where(WorkItem.site_id == other_site)).one()
    other_case = case_id_from(propose(outsider, other_item))
    other_rev = session.scalars(
        select(ChangeRevision).where(ChangeRevision.case_id == other_case)
    ).one()

    # 내 현장 ID를 붙여 남의 변경 버전을 확정하려는 요청
    response = client.post(f"/changes/{other_case}/revisions/{other_rev.id}/confirm",
                           data={"site_id": item.site_id, "confirm_key": "k"})  # fmt: skip

    assert response.status_code == 404
    session.expire_all()
    assert session.get(ChangeRevision, other_rev.id).status == "review"  # type: ignore[union-attr]


def test_list_shows_open_changes_and_all(
    client: TestClient, session: Session, item: WorkItem
) -> None:
    open_case = case_id_from(propose(client, item, title="진행 중 변경"))
    done_case = case_id_from(propose(client, item, title="끝난 변경"))
    done_rev = session.scalars(
        select(ChangeRevision).where(ChangeRevision.case_id == done_case)
    ).one()
    confirm(client, item, done_case, done_rev.id)

    open_page = client.get(f"/changes?site_id={item.site_id}").text
    all_page = client.get(f"/changes?site_id={item.site_id}&show=all").text

    assert f"/changes/{open_case}" in open_page and f"/changes/{done_case}" not in open_page
    assert f"/changes/{open_case}" in all_page and f"/changes/{done_case}" in all_page
    assert "자재" in open_page


def test_confirmed_change_makes_the_old_weather_judgment_need_rejudgment(
    client: TestClient, session: Session, item: WorkItem
) -> None:
    client.post("/judgments/run", data={"site_id": item.site_id})
    case_id = case_id_from(propose(client, item, after_work_date="2026-10-05",
                                   after_start="13:00", after_end="16:00"))  # fmt: skip
    confirm(client, item, case_id, revision(session).id)

    session.expire_all()  # 확정은 다른 요청(세션)에서 저장됐다
    view = judgments_service.build_dashboard(session, None, item.site_id, None, None, FIXED_NOW)

    assert view is not None
    assert view.cards[0].verdict is None and "작업 시간" in view.cards[0].reason


def test_database_keeps_one_current_version_per_case(
    client: TestClient, session: Session, item: WorkItem
) -> None:
    case_id = case_id_from(propose(client, item))
    confirm(client, item, case_id, revision(session).id)

    with pytest.raises(IntegrityError):
        session.execute(
            text(
                "INSERT INTO change_revisions (case_id, number, status, reasons,"
                " based_on_plan_version,"
                " before_work_date, before_start_local, before_end_local, before_location,"
                " after_work_date, after_start_local, after_end_local, after_location,"
                " proposed_by_user_id, proposed_at, confirmed_by_user_id, confirmed_at)"
                " SELECT case_id, 2, 'confirmed', reasons, 2, after_work_date, after_start_local,"
                " after_end_local, after_location, after_work_date, after_start_local,"
                " after_end_local, after_location, proposed_by_user_id, proposed_at,"
                " confirmed_by_user_id, confirmed_at FROM change_revisions WHERE number = 1"
            )
        )
        session.commit()
    session.rollback()
