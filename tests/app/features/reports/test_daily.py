"""작업일보·공사일보(C14-2, D-112). 가상 현장·가상 계정만 쓴다. 현재 시각은 2026-10-04(일) 15:00."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.features.reports.models import WorkReport
from app.features.schedules.models import WorkItem
from tests.app.features.actions.test_actions import SAFETY, item, participant_of
from tests.app.features.changes.test_changes import (
    OUTSIDER,
    SUB_USER,
    VIEWER,
    case_id_from,
    confirm,
    join,
    propose,
    revision,
)
from tests.conftest import Browser

__all__ = ["item"]


def work_on(client: TestClient, session: Session, site_id: int, day: str, start: str,
            end: str, performer: int) -> WorkItem:  # fmt: skip
    added = client.post(
        "/schedule",
        data={"site_id": site_id, "work_types": ["철골 작업"], "work_date": day, "work_dates": day,
              "start": start, "end": end, "performing_participant_id": performer},
        follow_redirects=False,
    )  # fmt: skip
    assert added.status_code == 303, added.text
    session.expire_all()
    return session.scalars(select(WorkItem).order_by(WorkItem.id.desc())).first()  # type: ignore[return-value]


def record(client: TestClient, w: WorkItem, **form: Any) -> Any:
    return client.post(
        f"/reports/{w.site_id}/daily/{w.id}",
        data={"outcome": "done", **form},
        follow_redirects=False,
    )


def saved(session: Session, w: WorkItem) -> WorkReport | None:
    session.expire_all()
    return session.scalar(select(WorkReport).where(WorkReport.work_item_id == w.id))


@pytest.fixture
def team(client: TestClient, browser: Browser, session: Session, item: WorkItem) -> dict[str, Any]:
    framer = join(client, browser, item.site_id, SUB_USER, "assignee")
    safety = join(client, browser, item.site_id, SAFETY, "assignee")
    return {
        "framer": framer,
        "safety": safety,
        "framer_company": participant_of(session, item.site_id, SUB_USER["email"]),
        "safety_company": participant_of(session, item.site_id, SAFETY["email"]),
    }


@pytest.fixture
def today_work(
    client: TestClient, session: Session, item: WorkItem, team: dict[str, Any]
) -> WorkItem:
    """오늘 16:00 골조 업체 작업(지금 15:00 이후라 오늘 등록할 수 있다)."""
    return work_on(client, session, item.site_id, "2026-10-04", "16:00", "18:00",
                   team["framer_company"])  # fmt: skip


def test_today_can_be_recorded_but_tomorrow_cannot(
    client: TestClient, session: Session, item: WorkItem, today_work: WorkItem
) -> None:
    assert record(client, today_work, workers="7").status_code == 303
    assert saved(session, today_work).workers == 7  # type: ignore[union-attr]

    tomorrow = record(client, item)  # 내일(10/5) 작업
    assert tomorrow.status_code == 422 and "작업일이 지나야" in tomorrow.text
    assert saved(session, item) is None
    assert "결과 기록" not in client.get(f"/reports/{item.site_id}/daily?day=2026-10-05").text


@pytest.mark.parametrize(
    ("workers", "ok"), [("-1", False), ("0", True), ("999", True), ("1000", False), ("일곱", False)]
)
def test_workers_range(
    client: TestClient, session: Session, today_work: WorkItem, workers: str, ok: bool
) -> None:
    response = record(client, today_work, workers=workers)
    assert (response.status_code == 303) is ok
    assert (saved(session, today_work) is not None) is ok


def test_short_work_needs_a_cause_and_done_keeps_none(
    client: TestClient, session: Session, today_work: WorkItem
) -> None:
    missing = record(client, today_work, outcome="not_done")
    assert missing.status_code == 422 and "원인을 하나 이상" in missing.text
    assert saved(session, today_work) is None
    assert record(client, today_work, outcome="not_done", causes="made-up").status_code == 422

    assert record(client, today_work, outcome="not_done", causes=["weather", "weather"],
                  note="오후 강풍").status_code == 303  # fmt: skip
    report = saved(session, today_work)
    assert report is not None and report.causes == ["weather"] and report.workers is None

    assert record(client, today_work, outcome="done", causes="weather").status_code == 303
    assert saved(session, today_work).causes == []  # type: ignore[union-attr]


def test_only_the_performing_company_or_coordinator_records(
    client: TestClient, browser: Browser, session: Session, today_work: WorkItem,
    team: dict[str, Any],
) -> None:  # fmt: skip
    assert record(team["safety"], today_work).status_code == 403  # 다른 업체 담당자
    viewer = join(client, browser, today_work.site_id, VIEWER, "viewer")
    assert record(viewer, today_work).status_code == 403
    assert record(browser(OUTSIDER), today_work).status_code == 404
    assert saved(session, today_work) is None

    assert record(team["framer"], today_work, outcome="partial", causes="labor").status_code == 303
    page = client.get(f"/reports/{today_work.site_id}/daily").text
    assert "일부만" in page and "인력" in page and "골조 담당" in page
    # 열람자는 보기만 한다
    assert "결과 기록" not in viewer.get(f"/reports/{today_work.site_id}/daily").text


def test_record_made_before_a_plan_change_is_marked_not_carried_over(
    client: TestClient, session: Session, today_work: WorkItem
) -> None:
    assert record(client, today_work, outcome="not_done", causes="material").status_code == 303
    case_id = case_id_from(propose(client, today_work))
    assert confirm(client, today_work, case_id, revision(session).id).status_code == 303

    moved = client.get(f"/reports/{today_work.site_id}/daily?day=2026-10-06").text
    assert "기록 뒤 계획 바뀜" in moved
    report = saved(session, today_work)
    assert report is not None and report.plan_version == 1  # 기록은 그대로, 새 계획으로 옮기지 않음


def test_totals_leave_unknown_workers_blank(
    client: TestClient, session: Session, item: WorkItem, today_work: WorkItem,
    team: dict[str, Any],
) -> None:  # fmt: skip
    page = client.get(f"/reports/{item.site_id}/daily").text
    assert "투입 인원</dt><dd>-" in page  # 아무도 안 적었으면 0명이 아니라 빈칸
    other = work_on(client, session, item.site_id, "2026-10-04", "16:30", "18:00",
                    team["safety_company"])  # fmt: skip
    record(client, today_work, workers="7")
    record(client, other)  # 인원 모름
    page = client.get(f"/reports/{item.site_id}/daily").text
    assert "투입 인원</dt><dd>7명" in page and "기록</dt><dd>2건" in page


def test_when_it_became_known_is_optional_and_cleared_for_done_work(
    client: TestClient, session: Session, today_work: WorkItem
) -> None:
    bad = record(client, today_work, outcome="partial", causes="material", known_when="yesterday")
    assert bad.status_code == 422 and "목록에서 골라" in bad.text

    assert record(client, today_work, outcome="partial", causes="material").status_code == 303
    assert saved(session, today_work).known_when is None  # type: ignore[union-attr]  # 고르지 않으면 모름

    assert record(client, today_work, outcome="partial", causes="material",
                  known_when="morning").status_code == 303  # fmt: skip
    assert saved(session, today_work).known_when == "morning"  # type: ignore[union-attr]
    assert "당일 아침 알게 됨" in client.get(f"/reports/{today_work.site_id}/daily").text

    assert record(client, today_work, outcome="done", known_when="morning").status_code == 303
    assert saved(session, today_work).known_when is None  # type: ignore[union-attr]


def test_mark_the_rest_done_leaves_recorded_and_other_companies_work(
    client: TestClient, session: Session, item: WorkItem, today_work: WorkItem,
    team: dict[str, Any],
) -> None:  # fmt: skip
    other = work_on(client, session, item.site_id, "2026-10-04", "16:30", "18:00",
                    team["safety_company"])  # fmt: skip
    third = work_on(client, session, item.site_id, "2026-10-04", "17:00", "18:00",
                    team["framer_company"])  # fmt: skip
    record(team["framer"], today_work, outcome="partial", causes="material")

    page = team["framer"].get(f"/reports/{item.site_id}/daily").text
    assert "남은 1건 모두 했음" in page  # 골조 담당이 기록할 수 있는 미입력은 third 하나
    done = team["framer"].post(f"/reports/{item.site_id}/daily/done-all",
                               data={"day": "2026-10-04"}, follow_redirects=False)  # fmt: skip
    assert done.status_code == 303
    assert saved(session, today_work).outcome == "partial"  # type: ignore[union-attr]  # 그대로
    assert saved(session, third).outcome == "done"  # type: ignore[union-attr]
    assert saved(session, other) is None  # 다른 업체 작업은 건드리지 않는다

    # 내일 작업은 한 번에 처리해도 들어가지 않는다
    client.post(f"/reports/{item.site_id}/daily/done-all", data={"day": "2026-10-05"})
    assert saved(session, item) is None
    assert team["framer"].post(f"/reports/{item.site_id}/daily/done-all",
                               data={"day": "2026-10-04"}).status_code == 200  # fmt: skip
