"""공정표 파일(CSV·XLSX) → 작업 행(C04-30, D-086).

열은 머리 줄의 이름으로 찾고, 공온이 쓰지 않는 열(인원·장비 등)은 무시한다. 값의 뜻(작업 목록·
업체·날짜 범위)은 여기서 판단하지 않고 service.import_items가 작업 추가와 같은 검사로 본다.
"""

import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime, time

MAX_IMPORT_BYTES = 1_000_000
MAX_IMPORT_ROWS = 300
# 머리 줄 이름 → 필드. 띄어쓰기는 무시하고 비교한다(예: '실행 업체').
HEADERS = {
    "날짜": "work_date",
    "작업일": "work_date",
    "시작": "start",
    "시작시각": "start",
    "종료": "end",
    "종료시각": "end",
    "작업": "work_type",
    "작업종류": "work_type",
    "위치": "location",
    "작업위치": "location",
    "실행업체": "company",
    "업체": "company",
    "메모": "memo",
}
REQUIRED = {"work_date": "날짜", "start": "시작", "end": "종료", "work_type": "작업",
            "company": "실행업체"}  # fmt: skip


class ImportFileError(ValueError):
    """파일 자체를 읽을 수 없거나 형식이 맞지 않음(행 오류와 구분)."""


@dataclass(frozen=True, slots=True)
class ImportRow:
    line: int  # 파일의 줄 번호(머리 줄 = 1부터 센 실제 줄)
    work_date: str
    start: str
    end: str
    work_type: str
    location: str
    company: str
    memo: str


def read_rows(filename: str, data: bytes) -> list[ImportRow]:
    """파일 이름의 확장자로 CSV·XLSX를 골라 읽는다. 빈 줄은 건너뛴다."""
    if not data:
        raise ImportFileError("빈 파일입니다.")
    if len(data) > MAX_IMPORT_BYTES:
        raise ImportFileError("파일이 너무 큽니다(1MB까지).")
    name = filename.lower()
    if name.endswith(".csv"):
        table = _csv_table(data)
    elif name.endswith(".xlsx"):
        table = _xlsx_table(data)
    else:
        raise ImportFileError("엑셀(.xlsx) 또는 CSV(.csv) 파일을 올려 주세요.")
    return _rows(table)


def _csv_table(data: bytes) -> list[tuple[int, list[str]]]:
    # 한국어 엑셀이 저장한 CSV는 대개 CP949다. UTF-8(BOM 포함)을 먼저 본다.
    for encoding in ("utf-8-sig", "cp949"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ImportFileError("CSV 글자 인코딩을 읽을 수 없습니다(UTF-8 또는 CP949로 저장).")
    reader = csv.reader(io.StringIO(text))
    return [(n, [c.strip() for c in row]) for n, row in enumerate(reader, start=1)]


def _xlsx_table(data: bytes) -> list[tuple[int, list[str]]]:
    from openpyxl import load_workbook  # 엑셀을 올릴 때만 불러온다

    try:
        book = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as error:  # 손상·암호 파일 등은 원인을 알려 주고 멈춘다
        raise ImportFileError(f"엑셀 파일을 열 수 없습니다({type(error).__name__}).") from error
    try:
        sheet = book.worksheets[0]
        return [
            (n, [_cell_text(c) for c in row])
            for n, row in enumerate(sheet.iter_rows(values_only=True), start=1)
        ]
    finally:
        book.close()


def _cell_text(value: object) -> str:
    """엑셀 칸 → 글자. 날짜·시각 칸은 서식이 아니라 값으로 바꾼다."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        if value.time() == time(0):
            return value.date().isoformat()
        return f"{value:%H:%M}" if value.date() <= date(1900, 1, 1) else value.isoformat(" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return f"{value:%H:%M}"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _rows(table: list[tuple[int, list[str]]]) -> list[ImportRow]:
    filled = [(n, row) for n, row in table if any(row)]
    if not filled:
        raise ImportFileError("파일에 내용이 없습니다.")
    _, head = filled[0]
    columns: dict[str, int] = {}
    for index, title in enumerate(head):
        field = HEADERS.get(re.sub(r"\s+", "", title))
        if field and field not in columns:
            columns[field] = index
    missing = [label for field, label in REQUIRED.items() if field not in columns]
    if missing:
        raise ImportFileError(
            f"첫 줄에 {', '.join(missing)} 열이 없습니다. 샘플 파일의 열 이름을 써 주세요."
        )
    body = filled[1:]
    if len(body) > MAX_IMPORT_ROWS:
        raise ImportFileError(f"한 번에 {MAX_IMPORT_ROWS}줄까지 올릴 수 있습니다.")

    def get(row: list[str], field: str) -> str:
        index = columns.get(field)
        return row[index] if index is not None and index < len(row) else ""

    return [
        ImportRow(
            line=line,
            work_date=_date_text(get(row, "work_date")),
            start=_time_text(get(row, "start")),
            end=_time_text(get(row, "end")),
            work_type=get(row, "work_type"),
            location=get(row, "location"),
            company=get(row, "company"),
            memo=get(row, "memo"),
        )
        for line, row in body
    ]


def _date_text(text: str) -> str:
    """2026.10.27 · 2026/10/27 · 2026-10-27 → 2026-10-27. 다른 모양은 그대로 둬 검사에서 걸린다."""
    match = re.fullmatch(r"(\d{4})[.\-/]\s*(\d{1,2})[.\-/]\s*(\d{1,2})\.?", text.strip())
    if not match:
        return text.strip()
    year, month, day = match.groups()
    return f"{year}-{int(month):02d}-{int(day):02d}"


def _time_text(text: str) -> str:
    """7:00 → 07:00. 초가 붙어 있으면(07:00:00) 뗀다."""
    match = re.fullmatch(r"(\d{1,2}):(\d{2})(?::\d{2})?", text.strip())
    return f"{int(match.group(1)):02d}:{match.group(2)}" if match else text.strip()
