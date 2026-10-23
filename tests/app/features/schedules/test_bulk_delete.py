"""함께 등록한 작업 한꺼번에 지우기·선택 지우기(C04-43, D-098). 지금은 2026-10-04 15:00 KST.

한 번에 여러 날을 등록하면 한 묶음이다. 묶음 지우기는 오늘 이후 남은 같은 묶음만, 선택 지우기는
고른 것 중 이 현장·오늘 이후 작업만 지운다. 다른 작업·지난 작업·다른 현장 작업은 그대로 남는다.
"""

from datetime import date, time

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.features.schedules.models import WorkItem
from tests.app.features.schedules.test_schedules import add_item, add_on_days, add_site
from tests.app.features.teams.test_nav import OTHER
from tests.conftest import Browser


def active(session: Session, site_id: int) -> list[WorkItem]:
    session.expire_all()
    rows = session.scalars(
        select(WorkItem)
        .where(WorkItem.site_id == site_id, WorkItem.deleted_at.is_(None))
        .order_by(WorkItem.work_date)
    )
    return list(rows)


def test_days_added_together_share_one_batch_but_a_single_add_has_none(
    client: TestClient, session: Session
) -> None:
    site_id = add_site(client)
    add_on_days(client, site_id, "2026-10-05", "2026-10-06", "2026-10-07")
    add_item(client, site_id, work_date="2026-10-08")

    items = active(session, site_id)

    assert len({i.batch_key for i in items[:3]}) == 1 and items[0].batch_key is not None
    assert items[3].batch_key is None


def test_batch_delete_removes_only_the_rest_of_that_batch_from_today(
    client: TestClient, session: Session
) -> None:
    site_id = add_site(client)
    add_on_days(client, site_id, "2026-10-05", "2026-10-06", "2026-10-07")
    add_item(client, site_id, work_date="2026-10-06", location="B구역")  # 다른 작업
    first = active(session, site_id)[0]
    past = WorkItem(site_id=site_id, work_type="철골 작업", work_date=date(2026, 10, 3),
                    start_local=time(9), end_local=time(12), location="A구역",
                    batch_key=first.batch_key)  # fmt: skip
    session.add(past)
    session.commit()
    page = client.get(f"/schedule?site_id={site_id}&day=2026-10-05").text

    response = client.post(f"/schedule/{first.id}/delete",
                           data={"site_id": site_id, "day": "2026-10-05", "scope": "batch"},
                           follow_redirects=False)  # fmt: skip

    assert "오늘 이후 남은 3건" in page  # 지난 작업은 세지 않는다
    assert response.headers["location"].endswith("deleted=3")
    left = active(session, site_id)
    assert [(i.work_date, i.location) for i in left] == [
        (date(2026, 10, 3), "A구역"), (date(2026, 10, 6), "B구역")
    ]  # fmt: skip


def test_scope_one_deletes_just_that_item(client: TestClient, session: Session) -> None:
    site_id = add_site(client)
    add_on_days(client, site_id, "2026-10-05", "2026-10-06")
    first = active(session, site_id)[0]

    client.post(f"/schedule/{first.id}/delete", data={"site_id": site_id, "scope": "one"})

    assert [i.work_date for i in active(session, site_id)] == [date(2026, 10, 6)]


def test_selected_delete_ignores_other_sites_and_past_items(
    client: TestClient, session: Session
) -> None:
    site_id = add_site(client)
    other_site = add_site(client, name="△△현장")
    add_on_days(client, site_id, "2026-10-05", "2026-10-06", "2026-10-07")
    add_item(client, other_site)
    mine = active(session, site_id)
    theirs = active(session, other_site)[0]
    past = WorkItem(site_id=site_id, work_type="철골 작업", work_date=date(2026, 10, 2),
                    start_local=time(9), end_local=time(12), location="")  # fmt: skip
    session.add(past)
    session.commit()

    response = client.post(
        "/schedule/delete-selected",
        data={"site_id": site_id, "day": "2026-10-05",
              "item_ids": [mine[0].id, mine[1].id, theirs.id, past.id]},
        follow_redirects=False,
    )  # fmt: skip

    assert response.headers["location"].endswith("deleted=2")
    assert [i.work_date for i in active(session, site_id)] == [date(2026, 10, 2), date(2026, 10, 7)]
    assert len(active(session, other_site)) == 1


def test_only_a_coordinator_can_delete_in_bulk(
    client: TestClient, browser: Browser, session: Session
) -> None:
    site_id = add_site(client)
    add_on_days(client, site_id, "2026-10-05", "2026-10-06")
    ids = [i.id for i in active(session, site_id)]
    outsider = browser(OTHER)

    selected = outsider.post(
        "/schedule/delete-selected",
        data={"site_id": site_id, "item_ids": ids},
        follow_redirects=False,
    )
    batch = outsider.post(
        f"/schedule/{ids[0]}/delete",
        data={"site_id": site_id, "scope": "batch"},
        follow_redirects=False,
    )

    assert selected.status_code in (403, 404) and batch.status_code in (403, 404)
    assert len(active(session, site_id)) == 2
