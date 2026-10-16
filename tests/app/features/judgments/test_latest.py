"""작업별 최신 판정 선정(C04-1, S08-4-3).

예전에는 판정 전체를 (50 곱하기 일수)행으로 자른 뒤 묶어서, 다른 작업의 판정이 쌓이면
오래 판정하지 않은 작업이 화면에서 빠졌다. 다른 공종 판정을 제한보다 많이 쌓아 재현한다.
"""

from datetime import date, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.features.judgments import repository
from app.features.judgments.models import Judgment
from tests.conftest import FIXED_NOW

TOMORROW = date(2026, 10, 5)
SITE: dict[str, Any] = {
    "name": "가상현장",
    "road_address": "서울 중구 세종대로 110",
    "latitude": "37.5665",
    "longitude": "126.9780",
    "work_start": "07:00",
    "work_end": "17:00",
    "work_start_date": "2026-10-01",
    "work_end_date": "2026-12-31",
    "work_types": ["철골 작업"],
}
ITEM = {"work_types": "철골 작업", "work_date": "2026-10-05", "start": "09:00", "end": "12:00"}
NOISE = 120  # 예전 제한(50행, 하루)보다 많다


def add_site(client: TestClient, name: str = "가상현장") -> int:
    response = client.post("/sites", data={**SITE, "name": name}, follow_redirects=False)
    return int(response.headers["location"].split("site_id=")[1].split("&")[0])


def judged_site_with_item(client: TestClient, session: Session, name: str = "가상현장") -> int:
    site_id = add_site(client, name)
    client.post("/schedule", data={**ITEM, "site_id": site_id})
    client.post("/judgments/run", data={"site_id": site_id})
    return site_id


def item_judgment(session: Session, site_id: int, day: date = TOMORROW) -> Judgment:
    return session.scalars(
        select(Judgment).where(
            Judgment.site_id == site_id,
            Judgment.target_date == day,
            Judgment.work_item_id.is_not(None),
            Judgment.work_type == "철골 작업",  # 그 작업의 폭염 판정은 빼고
        )
    ).one()


def clone(source: Judgment, **changes: Any) -> Judgment:
    columns = {c.key: getattr(source, c.key) for c in inspect(Judgment).columns if c.key != "id"}
    return Judgment(**{**columns, **changes})


def pile_up_other_work(session: Session, source: Judgment) -> None:
    """source와 같은 현장·날짜에 다른 공종의 더 새로운 판정을 많이 넣는다(예보 발표도 다름)."""
    session.add_all(
        clone(
            source,
            work_type=f"다른 공종 {n}",
            work_item_id=None,
            forecast_issued_at=FIXED_NOW - timedelta(minutes=n),
            judged_at=source.judged_at + timedelta(minutes=n + 1),
        )
        for n in range(NOISE)
    )
    session.commit()


def test_day_keeps_a_work_item_whose_judgment_is_older_than_many_others(
    client: TestClient, session: Session
) -> None:
    site_id = judged_site_with_item(client, session)
    target = item_judgment(session, site_id)
    pile_up_other_work(session, target)

    rows = repository.latest_for_site_date(session, site_id, TOMORROW)

    assert target.id in [r.id for r in rows]
    keys = [(r.work_type, r.work_item_id) for r in rows]
    assert len(keys) == len(set(keys))  # 작업마다 하나
    assert [r.judged_at for r in rows] == sorted((r.judged_at for r in rows), reverse=True)


def test_home_query_keeps_each_sites_work_item(client: TestClient, session: Session) -> None:
    first = judged_site_with_item(client, session, "가상현장1")
    second = judged_site_with_item(client, session, "가상현장2")
    sources = [item_judgment(session, first), item_judgment(session, second)]
    targets = {s.id for s in sources}
    for source in sources:
        pile_up_other_work(session, source)

    rows = repository.latest_for_sites_date(session, [first, second], TOMORROW)

    assert targets <= {r.id for r in rows}


def test_latest_judgment_per_work_replaces_its_own_older_one(
    client: TestClient, session: Session
) -> None:
    site_id = judged_site_with_item(client, session)
    old = item_judgment(session, site_id)
    newer = clone(old, forecast_issued_at=FIXED_NOW, judged_at=old.judged_at + timedelta(hours=1))
    session.add(newer)
    session.commit()

    rows = repository.latest_for_site_date(session, site_id, TOMORROW)

    ids = [r.id for r in rows]
    assert newer.id in ids and old.id not in ids


def test_week_keeps_latest_and_previous_forecast_per_work_despite_noise(
    client: TestClient, session: Session
) -> None:
    site_id = judged_site_with_item(client, session)
    first = item_judgment(session, site_id)
    second = clone(
        first,
        forecast_issued_at=first.forecast_issued_at + timedelta(hours=3),  # type: ignore[operator]
        judged_at=first.judged_at + timedelta(hours=3),
    )
    third = clone(
        first,
        forecast_issued_at=first.forecast_issued_at + timedelta(hours=6),  # type: ignore[operator]
        judged_at=first.judged_at + timedelta(hours=6),
    )
    session.add_all([second, third])
    session.commit()
    pile_up_other_work(session, first)

    rows = repository.latest_for_site_between(
        session, site_id, TOMORROW, TOMORROW + timedelta(days=6)
    )

    mine = [
        r.id for r in rows if (r.work_item_id, r.work_type) == (first.work_item_id, first.work_type)
    ]
    assert mine == [third.id, second.id]  # 현재와 직전 다른 예보, 가장 오래된 예보는 빠짐
