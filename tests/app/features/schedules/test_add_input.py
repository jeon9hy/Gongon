"""작업 추가 편의(C04-3, D-059): 여러 공종 한 번에, 기간+요일, 자주 쓴 공종 순서, 최근 시간, 복사.

하나라도 맞지 않으면 아무것도 저장하지 않고, 한 번에 만드는 작업은 100건까지다.
"""

import json
import re
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.rules import WORK_TYPE_LABELS
from app.core.work_kinds import WORK_KIND_NAMES, WORK_TRADES
from app.features.schedules.models import WorkItem

SITE: dict[str, Any] = {
    "name": "가상현장",
    "road_address": "서울 중구 세종대로 110",
    "latitude": "37.5665",
    "longitude": "126.9780",
    "work_start_date": "2026-10-01",
    "work_end_date": "2026-12-31",
}
TOMORROW = date(2026, 10, 5)  # 오늘(고정) 2026-10-04의 다음 날


def add_site(client: TestClient) -> int:
    response = client.post("/sites", data=SITE, follow_redirects=False)
    return int(response.headers["location"].split("site_id=")[1].split("&")[0])


def post(client: TestClient, site_id: int, **data: Any) -> Any:
    base = {"site_id": site_id, "start": "08:00", "end": "17:00"}
    return client.post("/schedule", data={**base, **data}, follow_redirects=False)


def days(n: int) -> list[str]:
    return [(TOMORROW + timedelta(days=i)).isoformat() for i in range(n)]


def count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(WorkItem)) or 0


@pytest.fixture
def site_id(client: TestClient) -> int:
    return add_site(client)


def test_several_work_types_on_several_days_make_one_item_each(
    client: TestClient, site_id: int, session: Session
) -> None:
    response = post(client, site_id, work_types=["철골 작업", "고소작업대"], work_dates=days(3))

    assert response.status_code == 303 and "day=2026-10-05" in response.headers["location"]
    pairs = set(session.execute(select(WorkItem.work_type, WorkItem.work_date)).all())
    assert pairs == {(w, TOMORROW + timedelta(days=i)) for w in ("철골 작업", "고소작업대")
                     for i in range(3)}  # fmt: skip


@pytest.mark.parametrize(
    ("types", "day_count", "saved"),
    [
        (["철골 작업", "고소작업대", "콘크리트 타설", "이동식 크레인"], 25, True),  # 100건
        (list(WORK_TYPE_LABELS),
         17, False),  # 102건
    ],
)  # fmt: skip
def test_at_most_one_hundred_items_at_once(
    client: TestClient,
    site_id: int,
    session: Session,
    types: list[str],
    day_count: int,
    saved: bool,
) -> None:
    response = post(client, site_id, work_types=types, work_dates=days(day_count))

    assert response.status_code == (303 if saved else 422)
    assert count(session) == (len(types) * day_count if saved else 0)
    if not saved:
        assert "100건까지" in response.text and "102건" in response.text


def test_range_with_weekdays_picks_only_those_days(
    client: TestClient, site_id: int, session: Session
) -> None:
    end = TOMORROW + timedelta(days=13)
    response = post(client, site_id, work_types=["철골 작업"], date_mode="range",
                    range_start=TOMORROW.isoformat(), range_end=end.isoformat(),
                    weekdays=["0", "2", "4"])  # fmt: skip

    assert response.status_code == 303
    saved = sorted(session.scalars(select(WorkItem.work_date)))
    expected = [TOMORROW + timedelta(days=i) for i in range(14)]
    assert saved == [d for d in expected if d.weekday() in (0, 2, 4)]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"range_end": "2026-10-04"}, "종료일은 시작일과 같거나"),
        ({"weekdays": []}, "요일을 하나 이상"),
        ({"range_start": "2026-10-03", "weekdays": [str(i) for i in range(7)]}, "지난 날짜"),
        ({"range_end": "2027-02-01"}, "92일까지"),
        ({"range_end": "2026-10-06", "weekdays": ["5", "6"]}, "해당 요일이 없습니다"),
        ({"range_start": "10월 5일"}, "날짜 형식"),
    ],
)
def test_bad_range_saves_nothing(
    client: TestClient, site_id: int, session: Session, changes: dict[str, Any], message: str
) -> None:
    weekdays = ["0", "1", "2", "3", "4"]
    data = {"work_types": ["철골 작업"], "date_mode": "range", "range_start": "2026-10-05",
            "range_end": "2026-10-16", "weekdays": weekdays, **changes}  # fmt: skip

    response = post(client, site_id, **data)

    assert response.status_code == 422 and message in response.text
    assert count(session) == 0


def test_range_reaching_outside_the_site_period_saves_nothing(
    client: TestClient, site_id: int, session: Session
) -> None:
    response = post(client, site_id, work_types=["철골 작업"], date_mode="range",
                    range_start="2026-12-28", range_end="2027-01-03",
                    weekdays=[str(i) for i in range(7)])  # fmt: skip

    assert response.status_code == 422 and "작업 기간" in response.text
    assert count(session) == 0


def kind_values(page: str, field_key: str | None = None) -> list[str]:
    """작업 고르기의 체크 상자 값(field_key를 주면 그 업무분야 칸만)."""
    if field_key is not None:
        page = page.split(f'data-kinds="{field_key}"')[1].split("</div>")[0]
    return re.findall(r'name="work_types" value="([^"]+)"', page)


def test_frequently_used_work_kinds_come_first_without_site_setting(
    client: TestClient, site_id: int
) -> None:
    before = client.get(f"/schedule?site_id={site_id}").text
    post(client, site_id, work_types=["아스팔트 포장"], work_dates=days(2))
    post(client, site_id, work_types=["벽체 철근 배근"], work_dates=days(1))

    after = client.get(f"/schedule?site_id={site_id}").text

    assert 'data-trade="recent"' not in before  # 쓴 적 없으면 '자주 쓴 작업' 없음
    assert kind_values(after, "recent-f0") == ["아스팔트 포장", "벽체 철근 배근"]  # 많이 쓴 순
    assert set(kind_values(after)) == set(kind_values(before)) == set(WORK_KIND_NAMES)


def test_work_kind_is_picked_by_trade_then_field(client: TestClient, site_id: int) -> None:
    page = client.get(f"/schedule?site_id={site_id}").text

    trades = re.findall(r'data-trade="(t\d+)"[^>]*><span class="wpick__name">([^<]+)', page)
    assert [name for _, name in trades] == [t.name for t in WORK_TRADES]
    rebar = next(key for key, name in trades if name == "철근ㆍ콘크리트공사업")
    assert "콘크리트 타설" in kind_values(page, f"{rebar}-f0")
    assert page.index("법령 업종 밖") < page.index("전기·정보통신·소방")


def test_work_kind_outside_the_weather_list_is_saved(
    client: TestClient, site_id: int, session: Session
) -> None:
    response = post(
        client, site_id, work_types=["벽체 철근 배근", "벽체 철근 배근"], work_dates=days(1)
    )

    assert response.status_code == 303
    assert count(session) == 1  # 같은 작업이 여러 칸에서 함께 체크돼도 한 건


def test_add_form_times_are_not_prefilled(client: TestClient, site_id: int) -> None:
    post(client, site_id, work_types=["철골 작업"], work_dates=days(1), start="07:30",
         end="11:00")  # fmt: skip

    page = client.get(f"/schedule?site_id={site_id}&day=2026-10-05").text

    assert "data-time=" not in page  # 시간 바로가기 칩은 없앴다(D-065)
    assert 'name="start" value=""' in page and 'name="end" value=""' in page


def test_copy_button_carries_the_item_to_the_add_form(client: TestClient, site_id: int) -> None:
    post(client, site_id, work_types=["철골 작업"], work_dates=days(1), location="A구역",
         memo="양중")  # fmt: skip

    page = client.get(f"/schedule?site_id={site_id}&day=2026-10-05").text
    raw = re.search(r"data-copy='([^']+)'", page)

    assert raw is not None
    copied = json.loads(raw.group(1))
    performer = copied.pop("performer")
    expected = {"workType": "철골 작업", "start": "08:00", "end": "17:00", "location": "A구역",
                "memo": "양중"}  # fmt: skip
    assert copied == expected and performer.isdigit()  # 실행 업체도 함께 옮긴다


def test_picked_work_comes_back_as_removable_tokens_after_an_error(
    client: TestClient, site_id: int
) -> None:
    response = post(client, site_id, work_types=["벽체 철근 배근"], work_dates=days(1), start="9시")

    assert response.status_code == 422
    # 폼 칩과 작업 고르기 아래 토큰 두 곳에, 하나씩 빼는 버튼과 함께 다시 보인다.
    assert response.text.count('data-unpick="벽체 철근 배근"') == 2
