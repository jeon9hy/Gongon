"""공정표 가져오기(C04-30, D-086): 파일 읽기, 행 검사, 전부 아니면 전무, 같은 파일 다시 올리기.

실패 위험: 한국어 엑셀 CSV(CP949)·엑셀 날짜 칸을 못 읽음, 일부 줄만 저장돼 반쯤 들어감, 같은 파일을
두 번 올려 작업이 두 벌 생김, 다른 현장 업체 이름으로 등록됨.
"""

import io
from datetime import date, datetime, time
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.features.schedules.importer import ImportFileError, read_rows
from app.features.schedules.models import WorkItem
from app.features.schedules.schemas import WorkItemRecord
from app.features.schedules.service import UNASSIGNED, group_items, place_key
from tests.conftest import DEFAULT_PARTNER

SITE: dict[str, Any] = {
    "name": "가상현장",
    "road_address": "서울 중구 세종대로 110",
    "latitude": "37.5665",
    "longitude": "126.9780",
    "work_start_date": "2026-10-01",
    "work_end_date": "2026-12-31",
}
HEAD = "날짜,시작,종료,작업,위치,실행업체,메모,인원"


def csv_bytes(*lines: str, encoding: str = "utf-8-sig") -> bytes:
    return "\n".join((HEAD, *lines)).encode(encoding)


def add_site(client: TestClient) -> int:
    response = client.post("/sites", data=SITE, follow_redirects=False)
    site_id = int(response.headers["location"].split("site_id=")[1].split("&")[0])
    client._partner(site_id)  # type: ignore[attr-defined]  # 기본 협력업체를 참여 업체로
    return site_id


def upload(client: TestClient, site_id: int, data: bytes, name: str = "공정표.csv") -> Any:
    return client.post(
        "/schedule/import",
        data={"site_id": str(site_id)},
        files={"file": (name, data, "application/octet-stream")},
        follow_redirects=False,
    )


def count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(WorkItem)) or 0


GOOD = (
    f"2026-10-05,07:00,15:00,콘크리트 타설,101동 9층,{DEFAULT_PARTNER},레미콘 200㎥,8",
    f"2026.10.06,7:00,17:00,벽체 철근 배근,101동 10층 2구역,{DEFAULT_PARTNER},,12",
)


def test_csv_rows_are_registered_with_the_named_company(
    client: TestClient, session: Session
) -> None:
    site_id = add_site(client)

    response = upload(client, site_id, csv_bytes(*GOOD))

    assert response.status_code == 303 and "imported=2" in response.headers["location"]
    items = session.scalars(select(WorkItem).order_by(WorkItem.work_date)).all()
    assert [(i.work_type, i.work_date, i.start_local, i.location) for i in items] == [
        ("콘크리트 타설", date(2026, 10, 5), time(7), "101동 9층"),
        ("벽체 철근 배근", date(2026, 10, 6), time(7), "101동 10층 2구역"),  # 2026.10.06·7:00
    ]
    assert all(i.performing_participant_id is not None for i in items)


def test_same_file_twice_does_not_make_a_second_copy(client: TestClient, session: Session) -> None:
    site_id = add_site(client)
    upload(client, site_id, csv_bytes(*GOOD))

    again = upload(client, site_id, csv_bytes(*GOOD, GOOD[0]))  # 파일 안 반복도 한 건

    assert "imported=0" in again.headers["location"] and "skipped=3" in again.headers["location"]
    assert count(session) == 2


@pytest.mark.parametrize(
    ("line", "message"),
    [
        (f"2026-10-07,08:00,12:00,없는 작업,,{DEFAULT_PARTNER},,", "목록에 있는 작업"),
        ("2026-10-07,08:00,12:00,콘크리트 타설,,모르는건설,,", "참여 업체가 아닙니다"),
        (f"2026-10-03,08:00,12:00,콘크리트 타설,,{DEFAULT_PARTNER},,", "지난 날짜"),
        (f"2027-02-01,08:00,12:00,콘크리트 타설,,{DEFAULT_PARTNER},,", "작업 기간"),
        (f"2026-10-07,12:00,08:00,콘크리트 타설,,{DEFAULT_PARTNER},,", "종료는 시작보다"),
    ],
)
def test_one_bad_row_saves_nothing_and_names_the_line(
    client: TestClient, session: Session, line: str, message: str
) -> None:
    site_id = add_site(client)

    response = upload(client, site_id, csv_bytes(*GOOD, line))

    assert response.status_code == 422
    assert "4행:" in response.text and message in response.text  # 머리 줄이 1행
    assert count(session) == 0


def test_korean_excel_csv_in_cp949_is_read() -> None:
    rows = read_rows("공정표.csv", csv_bytes(*GOOD, encoding="cp949"))

    assert [r.work_type for r in rows] == ["콘크리트 타설", "벽체 철근 배근"]


def test_xlsx_date_and_time_cells_are_read_as_values() -> None:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    # 열 순서·띄어쓰기가 달라도 이름으로 찾는다
    sheet.append(["작업 위치", "날짜", "시작", "종료", "작업", "실행 업체", "장비"])
    excel_day = datetime(2026, 10, 5)  # noqa: DTZ001 - 엑셀 날짜 칸에는 시간대가 없다
    sheet.append(
        ["101동 9층", excel_day, time(7, 30), time(15), "콘크리트 타설", "대성골조", "펌프카"]
    )
    buffer = io.BytesIO()
    book.save(buffer)

    (row,) = read_rows("공정표.xlsx", buffer.getvalue())

    assert (row.work_date, row.start, row.end, row.location, row.company) == (
        "2026-10-05", "07:30", "15:00", "101동 9층", "대성골조",
    )  # fmt: skip


@pytest.mark.parametrize(
    ("name", "data", "message"),
    [
        (
            "공정표.csv",
            "날짜,작업\n2026-10-05,콘크리트 타설".encode(),
            "시작, 종료, 실행업체 열이 없습니다",
        ),
        ("공정표.pdf", b"x", "엑셀(.xlsx) 또는 CSV"),
        ("공정표.xlsx", b"not a zip", "엑셀 파일을 열 수 없습니다"),
        ("공정표.csv", b"", "빈 파일"),
    ],
)
def test_unreadable_file_explains_why(name: str, data: bytes, message: str) -> None:
    with pytest.raises(ImportFileError, match=message.replace("(", r"\(").replace(")", r"\)")):
        read_rows(name, data)


def test_place_key_takes_building_and_floor_only() -> None:
    assert place_key("101동 9층 2구역") == "101동 9층"
    assert place_key("101동 외벽 3~5층") == "101동 3~5층"
    assert place_key("102동 지하 1층 기계실") == "102동 지하1층"
    assert place_key("자재 야적장") == "자재 야적장"  # 동·층이 없으면 적은 그대로
    assert place_key("  ") == "위치 없음"


def test_items_without_company_group_first_as_unassigned() -> None:
    def item(item_id: int, performer: int | None) -> WorkItemRecord:
        return WorkItemRecord(item_id, 1, "콘크리트 타설", date(2026, 10, 5), time(7), time(9), "",
                              "", performer)  # fmt: skip

    groups = group_items([item(1, 7), item(2, None)], "company", {7: "가나건설"})

    assert [(label, [i.item_id for i in items]) for label, items in groups] == [
        (UNASSIGNED, [2]),
        ("가나건설", [1]),
    ]
    assert UNASSIGNED == "업체 미정"
