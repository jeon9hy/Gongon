"""작업 일정 입력(S08-1)과 작업별 판정 연결. 기상청은 가짜(FakeKma), 지금은 2026-10-04 15:00 KST."""

import re
from datetime import date, time
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.features.judgments.models import Judgment
from app.features.schedules.models import WorkItem
from engine.kst import KST
from tests.conftest import FIXED_NOW
from tests.fakes import FakeKma

SITE: dict[str, Any] = {
    "name": "○○현장",
    "road_address": "서울 중구 세종대로 110",
    "latitude": "37.5665",
    "longitude": "126.9780",
    "work_start": "07:00",
    "work_end": "17:00",
    "work_start_date": "2026-10-01",
    "work_end_date": "2026-12-31",
    "work_types": ["철골 작업", "고소작업대"],
}
ITEM: dict[str, str] = {
    "work_types": "철골 작업",
    "work_date": "2026-10-05",  # 내일(판정 대상)
    "start": "09:00",
    "end": "12:00",
    "location": "A구역",
}
STEEL = Judgment.work_type == "철골 작업"


def add_site(client: TestClient, **changes: Any) -> int:
    location = client.post("/sites", data={**SITE, **changes}, follow_redirects=False).headers[
        "location"
    ]
    return int(location.split("site_id=")[1].split("&")[0])


def add_item(client: TestClient, site_id: int, **changes: str) -> Any:
    data = {**ITEM, **changes, "site_id": str(site_id)}
    return client.post("/schedule", data=data, follow_redirects=False)


def run(client: TestClient, site_id: int) -> None:
    response = client.post("/judgments/run", data={"site_id": site_id}, follow_redirects=False)
    assert response.status_code == 303


def test_item_is_saved_and_listed_under_its_day(client: TestClient) -> None:
    site_id = add_site(client)
    response = add_item(client, site_id)
    assert response.status_code == 303
    page = client.get(response.headers["location"]).text
    assert "작업을 추가했습니다" in page
    assert "09:00–12:00" in page and "A구역" in page


def test_navigation_keeps_the_selected_site_through_judgment_detail(
    client: TestClient, session: Session
) -> None:
    add_site(client, name="첫 현장")
    site_id = add_site(client, name="선택한 현장")
    add_item(client, site_id)
    run(client, site_id)
    judgment = session.scalar(select(Judgment).where(Judgment.site_id == site_id, STEEL))
    assert judgment is not None
    for path in (
        f"/dashboard?site_id={site_id}",
        f"/schedule?site_id={site_id}",
        f"/sites?site_id={site_id}",
        f"/judgments?site_id={site_id}",
        f"/judgments/{judgment.id}",
    ):
        response = client.get(path)
        assert response.status_code == 200
        navigation = response.text.split('<nav class="appnav"')[1].split("</nav>")[0]
        for destination in ("schedule", "sites"):
            assert f'href="/{destination}?site_id={site_id}"' in navigation
        assert "/dashboard" not in navigation and "/judgments" not in navigation  # 하위 메뉴로
    for path in (f"/dashboard?site_id={site_id}", f"/schedule?site_id={site_id}"):
        page = client.get(path).text
        subnav = page.split('<nav class="subnav"')[1].split("</nav>")[0]
        assert f'href="/dashboard?site_id={site_id}"' in subnav
        assert f'href="/schedule?site_id={site_id}"' in subnav
        assert 'href="/judgments"' in subnav  # 판정 내역은 늘 전체 현장으로 연다
    assert '<nav class="subnav"' not in client.get(f"/sites?site_id={site_id}").text


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"work_types": "고소작업대 아님"}, "목록에 있는 공종"),
        ({"work_types": ""}, "공종을 하나 이상"),
        ({"work_date": "2026-10-03"}, "지난 날짜"),  # 어제(오늘은 허용, C04-4)
        ({"work_date": "2027-01-01"}, "작업 기간"),  # 현장 기간 밖
        ({"start": "12:00", "end": "12:00"}, "종료는 시작보다"),
        ({"start": "9시"}, "00:00 형식"),
        ({"location": "가" * 61}, "60자 이하"),
    ],
)
def test_invalid_item_is_rejected_and_not_saved(
    client: TestClient, session: Session, changes: dict[str, str], message: str
) -> None:
    site_id = add_site(client)
    response = add_item(client, site_id, **changes)
    assert response.status_code == 422
    assert message in response.text
    assert session.scalars(select(WorkItem)).first() is None


def test_item_of_another_site_cannot_be_deleted(client: TestClient, session: Session) -> None:
    mine = add_site(client)
    other = add_site(client, name="△△현장")
    add_item(client, mine)
    item_id = session.scalars(select(WorkItem.id)).one()

    response = client.post(f"/schedule/{item_id}/delete", data={"site_id": other})

    assert response.status_code == 404
    assert session.scalars(select(WorkItem.deleted_at)).one() is None


def test_items_are_judged_separately_and_rerun_adds_nothing(
    client: TestClient, session: Session, fake_kma: FakeKma
) -> None:
    fake_kma.set_hour("20261005", 14, WSD="12.0")  # 14시만 강풍
    site_id = add_site(client)
    add_item(client, site_id)  # 09~12 A구역: 강풍 시각 밖
    add_item(client, site_id, start="13:00", end="16:00", location="B구역")  # 강풍 시각 포함

    run(client, site_id)
    run(client, site_id)  # 같은 예보·기준·작업이면 다시 저장하지 않는다

    steel = session.scalars(select(Judgment).where(STEEL).order_by(Judgment.id)).all()
    assert [
        (j.work_start_at.astimezone(KST).hour, j.work_end_at.astimezone(KST).hour, j.verdict)
        for j in steel
    ] == [
        (9, 12, "진행"),
        (13, 16, "중지 검토"),
    ]
    assert all(j.work_item_id is not None for j in steel)
    # 그날 작업이 있으면 작업에 없는 공종(고소작업대)은 현장 기본 시간으로 따로 판정하지 않는다.
    types = set(session.scalars(select(Judgment.work_type)).all())
    assert types == {"철골 작업", "폭염(공통)"}

    dashboard = client.get(f"/dashboard?site_id={site_id}").text
    assert "철골 작업 · A구역" in dashboard and "철골 작업 · B구역" in dashboard


def test_day_without_items_is_not_judged(
    client: TestClient, session: Session, fake_kma: FakeKma
) -> None:
    # D-059: 현장 기본 공종·시간으로 대신 판정하지 않는다. 작업이 있는 날만 판정한다.
    for hour in range(24):
        fake_kma.set_hour("20261006", hour, PCP="강수없음", WSD="2.0", SNO="적설없음", TMP="20",
                          REH="50")  # fmt: skip
    site_id = add_site(client)
    add_item(client, site_id, work_date="2026-10-06")

    run(client, site_id)

    days = {j.target_date.isoformat() for j in session.scalars(select(Judgment))}
    assert days == {"2026-10-06"}
    assert all(j.work_item_id is not None for j in session.scalars(select(Judgment)))


def test_deleting_item_keeps_its_saved_judgment(client: TestClient, session: Session) -> None:
    site_id = add_site(client)
    add_item(client, site_id)
    run(client, site_id)
    item_id = session.scalars(select(WorkItem.id)).one()

    response = client.post(f"/schedule/{item_id}/delete", data={"site_id": site_id},
                           follow_redirects=False)  # fmt: skip

    assert response.status_code == 303
    session.expire_all()
    steel = session.scalars(select(Judgment).where(STEEL)).one()
    assert steel.work_item_id == item_id  # 판정과 당시 작업의 연결이 남는다(숨김 삭제, C04-1)
    assert session.get(WorkItem, item_id).deleted_at == FIXED_NOW  # type: ignore[union-attr]
    assert "09:00–12:00" not in client.get(f"/schedule?site_id={site_id}&day=2026-10-05").text


def test_deleting_two_identical_judged_items_does_not_collide(
    client: TestClient, session: Session
) -> None:
    # S08-4-2 재현: 같은 공종·시간 작업 둘을 판정한 뒤 지우면 두 번째 삭제가 고유 키 위반(500).
    site_id = add_site(client)
    add_item(client, site_id)
    add_item(client, site_id)
    run(client, site_id)
    item_ids = list(session.scalars(select(WorkItem.id).order_by(WorkItem.id)))
    assert len(item_ids) == 2

    statuses = [
        client.post(
            f"/schedule/{i}/delete", data={"site_id": site_id}, follow_redirects=False
        ).status_code
        for i in item_ids
    ]
    again = client.post(f"/schedule/{item_ids[0]}/delete", data={"site_id": site_id})

    assert statuses == [303, 303]
    assert again.status_code == 404  # 이미 지운 작업
    session.expire_all()
    linked = session.scalars(select(Judgment.work_item_id).where(STEEL)).all()
    assert sorted(i for i in linked if i is not None) == item_ids and None not in linked


def test_rerun_after_delete_does_not_judge_the_deleted_item(
    client: TestClient, session: Session, fake_kma: FakeKma
) -> None:
    site_id = add_site(client)
    add_item(client, site_id)
    item_id = session.scalars(select(WorkItem.id)).one()
    client.post(f"/schedule/{item_id}/delete", data={"site_id": site_id})
    response = client.post("/judgments/run", data={"site_id": site_id}, follow_redirects=False)

    assert "ran=no_work" in response.headers["location"]  # 남은 작업이 없으면 판정하지 않는다
    assert session.scalar(select(Judgment.id)) is None
    assert fake_kma.calls == []  # 예보도 받지 않는다


def test_dashboard_opens_when_first_card_has_daily_elements(
    client: TestClient, fake_kma: FakeKma
) -> None:
    # 회귀: 콘크리트(일평균기온 등 하루 단위 요소)가 대표 판정이면 그래프 탭 만들다 500이 났다.
    for hour in range(24):
        fake_kma.set_hour("20261006", hour, TMP="20", REH="50", PCP="강수없음", WSD="2.0")
    site_id = add_site(client)
    add_item(client, site_id, work_types="콘크리트 타설", start="07:00", end="17:00")
    run(client, site_id)

    response = client.get(f"/dashboard?site_id={site_id}")

    assert response.status_code == 200
    assert "콘크리트 타설" in response.text


# ---------- 월 달력 ----------


def test_month_grid_starts_on_sunday_and_selects_today(client: TestClient) -> None:
    site_id = add_site(client)
    page = client.get(f"/schedule?site_id={site_id}").text  # 지금 10/4 → 오늘이 든 10월
    assert "2026년 10월" in page
    # 10월 1일은 목요일 → 달력은 9월 27일(일)부터, 10월 31일(토)까지 5주(D-065 일요일 시작)
    assert page.count('<td class="calcell') == 35
    assert 'day=2026-10-01"' in page and 'day=2026-10-31"' in page
    # 작업 기간(10/1~) 밖의 9월 칸은 보이지만 누를 수 없다(개발자 요청 2026-10-16)
    assert 'day=2026-09-27"' not in page and 'aria-label="9월 27일, 작업 기간 밖"' in page
    selected = (
        f'href="/schedule?site_id={site_id}&amp;month=2026-10&amp;day=2026-10-04" '
        'aria-label="10월 4일, 작업 0건" aria-current="date"'
    )
    assert selected in page  # 오늘이 기본 선택(C04-4)
    assert "month=2026-11" in page  # 다음 달
    assert 'aria-label="이전 달(작업 기간 밖)"' in page  # 9월은 기간 밖이라 막힘


def test_month_outside_work_period_opens_the_nearest_period_month(client: TestClient) -> None:
    site_id = add_site(client)  # 작업 기간 2026-10-01~2026-12-31

    before = client.get(f"/schedule?site_id={site_id}&month=2026-05").text
    after = client.get(f"/schedule?site_id={site_id}&month=2027-03").text

    assert "2026년 10월" in before
    assert "2026년 12월" in after and 'aria-label="다음 달(작업 기간 밖)"' in after


def test_cell_shows_five_dots_and_counts_the_rest(client: TestClient) -> None:
    site_id = add_site(client)
    for hour in (8, 9, 10, 11, 12, 13):
        add_item(client, site_id, start=f"{hour:02d}:00", end=f"{hour:02d}:30")
    page = client.get(f"/schedule?site_id={site_id}&day=2026-10-05").text
    cell = page.split('aria-label="10월 5일, 작업 6건"')[1].split("</td>")[0]
    assert cell.count('class="dot dot--btn"') == 5 and ">+1</a>" in cell  # 점 5개 + 나머지
    assert page.count('class="workcard"') == 6  # 상세 패널에는 여섯 건 모두
    assert "11:00–11:30" in page


@pytest.mark.parametrize("query", ["month=2026-13", "month=abc", "day=2026-02-30", "day=x"])
def test_malformed_month_or_day_falls_back(client: TestClient, query: str) -> None:
    site_id = add_site(client)
    response = client.get(f"/schedule?site_id={site_id}&{query}")
    assert response.status_code == 200
    assert "2026년 10월" in response.text


def test_past_day_shows_detail_without_add_button(client: TestClient) -> None:
    site_id = add_site(client)
    page = client.get(f"/schedule?site_id={site_id}&day=2026-10-03").text  # 어제
    assert "지난 날짜는 작업을 추가할 수 없습니다" in page
    assert 'type="button" data-open-add' not in page  # 모달 자체는 있어도 여는 버튼이 없다


def month_menu(page: str) -> str:
    return page.split('class="monthpick__menu"')[1].split("</details>")[0]


def month_classes(menu: str, month: str) -> set[str]:
    """달 고르기 목록에서 그 달 링크의 class 목록."""
    found = re.search(rf'<a class="([^"]*)" href="[^"]*month={month}"', menu)
    assert found is not None, month
    return set(found.group(1).split())


def test_month_picker_spans_six_months_each_way_and_marks_the_work_period(
    client: TestClient,
) -> None:
    # 작업 기간 2026-10-01~2026-12-31, 보고 있는 달 10월 → 2026-04~2027-04, 10~12월만 작업 기간.
    site_id = add_site(client)

    menu = month_menu(client.get(f"/schedule?site_id={site_id}").text)

    # 한 해를 3줄 4칸으로 보이므로 2026·2027년 열두 달을 모두 두고, 기간 밖 달은 링크 없이 막는다
    assert "2026년" in menu and "2027년" in menu
    assert menu.count('class="monthpick__month') == 24
    assert 'aria-current="true">10월</a>' in menu
    for month in ("2026-10", "2026-11", "2026-12"):
        assert "is-period" in month_classes(menu, month)
    for month in ("2026-09", "2027-01"):  # 기간 바로 앞뒤 달
        assert f"month={month}" not in menu


def test_month_picker_marks_a_month_with_only_a_few_period_days(client: TestClient) -> None:
    site_id = add_site(client, work_end_date="2027-01-03")  # 1월은 3일만 기간 안

    menu = month_menu(client.get(f"/schedule?site_id={site_id}").text)

    assert "is-period" in month_classes(menu, "2027-01")
    assert "month=2027-02" not in menu


@pytest.mark.parametrize("missing", ["work_types", "start", "end"])
def test_item_without_a_required_value_is_not_saved_and_modal_reopens(
    client: TestClient, session: Session, missing: str
) -> None:
    site_id = add_site(client)

    response = add_item(client, site_id, **{missing: ""})

    assert response.status_code == 422
    assert session.scalar(select(WorkItem.id)) is None
    assert 'id="add-item" aria-labelledby="add-item-title" data-open' in response.text


def test_add_form_has_no_preselected_work_type_or_times(client: TestClient) -> None:
    site_id = add_site(client)

    page = client.get(f"/schedule?site_id={site_id}").text

    assert 'name="work_types"' in page and 'name="work_types" value="철골 작업" checked' not in page
    assert 'name="start" value=""' in page and 'name="end" value=""' in page


def add_on_days(client: TestClient, site_id: int, *days: str) -> Any:
    data: dict[str, Any] = {**ITEM, "work_date": "", "site_id": str(site_id)}
    if days:
        data["work_dates"] = list(days)
    return client.post("/schedule", data=data, follow_redirects=False)


def test_picked_dates_add_one_item_per_day(client: TestClient, session: Session) -> None:
    site_id = add_site(client)

    response = add_on_days(client, site_id, "2026-10-09", "2026-10-05", "2026-10-07")

    assert response.status_code == 303
    assert "day=2026-10-05" in response.headers["location"]  # 가장 이른 날로 돌아간다
    days = sorted(d.isoformat() for d in session.scalars(select(WorkItem.work_date)))
    assert days == ["2026-10-05", "2026-10-07", "2026-10-09"]


@pytest.mark.parametrize(
    ("days", "message"),
    [
        (("2026-10-05", "2026-10-03"), "지난 날짜"),  # 하나라도 지난 날이면 아무것도 만들지 않는다
        (("2026-10-05", "2027-01-03"), "작업 기간"),
        ((), "작업 날짜를 고르세요"),
    ],
)
def test_bad_picked_dates_save_nothing(
    client: TestClient, session: Session, days: tuple[str, ...], message: str
) -> None:
    site_id = add_site(client)

    response = add_on_days(client, site_id, *days)

    assert response.status_code == 422 and message in response.text
    assert session.scalar(select(WorkItem.id)) is None


def test_date_picker_disables_days_that_cannot_take_work(client: TestClient) -> None:
    site_id = add_site(client)

    page = client.get(f"/schedule?site_id={site_id}").text

    # 날짜 달력은 화면에서 그린다. 첫 날(오늘)·현장 기간·처음 고른 날(오늘)을 넘겨준다(D-064)
    assert 'data-min="2026-10-04" data-start="2026-10-01" data-end="2026-12-31"' in page
    assert 'data-initial="2026-10-04"' in page


def test_today_work_can_be_added_and_is_shown_without_judgment(
    client: TestClient, session: Session
) -> None:
    """오늘(경계)은 추가할 수 있다(어제는 위 검사가 막는다). 지금(15:00) 뒤 시작이어야 한다."""
    site_id = add_site(client)

    response = add_item(client, site_id, work_date="2026-10-04", start="15:01", end="17:00")

    assert response.status_code == 303
    assert [d.isoformat() for d in session.scalars(select(WorkItem.work_date))] == ["2026-10-04"]
    page = client.get(response.headers["location"]).text
    assert "15:01<span>–</span>17:00" in page and "오늘 먼저 챙길 것" in page


@pytest.mark.parametrize("start", ["14:59", "15:00"])  # 바로 앞·같은 분은 이미 시작한 것으로 본다
def test_today_work_must_start_after_now(client: TestClient, session: Session, start: str) -> None:
    site_id = add_site(client)

    response = add_item(client, site_id, work_date="2026-10-04", start=start, end="17:00")

    assert response.status_code == 422 and "지금(15:00) 이후 시작" in response.text
    assert session.scalar(select(WorkItem.id)) is None


def test_started_today_work_can_change_end_but_not_move_start_into_the_past(
    client: TestClient, session: Session
) -> None:
    """이미 시작한 오늘 작업(14:00)은 끝 시각을 고칠 수 있다. 시작을 다른 과거로는 못 옮긴다."""
    site_id = add_site(client)
    started = WorkItem(
        site_id=site_id,
        work_type="철골 작업",
        work_date=date(2026, 10, 4),
        start_local=time(14, 0),
        end_local=time(16, 0),
        location="",
        memo="",
    )
    session.add(started)
    session.commit()
    item_id = session.scalars(select(WorkItem.id)).one()

    def edit(start: str, end: str) -> Any:
        return client.post(
            f"/schedule/{item_id}/edit",
            data={"site_id": site_id, "day": "2026-10-04", "plan_version": "1",
                  "work_date": "2026-10-04", "start": start, "end": end},
            follow_redirects=False,
        )  # fmt: skip

    assert edit("13:00", "16:00").status_code == 422  # 다른 과거 시각으로
    assert edit("14:00", "18:00").status_code == 303  # 시작 그대로, 끝만 늘림
    session.expire_all()
    assert session.scalars(select(WorkItem.end_local)).one() == time(18, 0)
