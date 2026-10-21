"""공정표 가져오기(C04-30) 샘플 엑셀을 만든다. 내용은 합성 레퍼런스 공정표다(D-056, 실제 현장 아님).

docs/research/weekly-schedule-sample.csv(2주 골조 공정)를 공온 작업 이름·위치 글자로 바꾸고, 날짜를
--start(월요일) 기준으로 옮긴다. 업체 이름은 시연 현장(scripts/seed_demo.py)과 같다. 한빛설비는 시연
자료에 없으니 올리기 전에 참여 업체로 등록한다.

    PYTHONUTF8=1 uv run python scripts/make_schedule_sample.py --start 2026-11-02 \\
        --out app/core/static/samples/gongon-schedule-sample.xlsx
"""

import argparse
import csv
import sys
from datetime import date, timedelta
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "research" / "weekly-schedule-sample.csv"
REFERENCE_MONDAY = date(2026, 11, 2)  # 레퍼런스 공정표의 첫 월요일
HEAD = ("날짜", "시작", "종료", "작업", "위치", "실행업체", "메모")
# 레퍼런스 작업ID의 끝부분 → 공온 작업 이름(app/core/work_kinds.py)
KINDS = {
    "청소": "타설 전 청소", "검측": "검측(감리 입회)", "타설": "콘크리트 타설",
    "품질시험": "현장 품질시험", "양생": "양생", "먹매김": "먹매김", "형틀해체": "탈형(형틀 해체)",
    "갱폼인양": "갱폼 인양", "벽체철근": "벽체 철근 배근", "벽체전기": "전기 배관 매립",
    "벽체형틀": "벽체 형틀 설치", "코어형틀": "벽체 형틀 설치", "벽체형틀마감": "벽체 형틀 설치",
    "슬라브형틀": "슬라브 형틀 설치", "슬라브형틀1": "슬라브 형틀 설치",
    "슬라브형틀2": "슬라브 형틀 설치", "슬라브철근": "슬라브 철근 배근",
    "슬라브전기": "전기 배관 매립", "설비슬리브": "설비 슬리브 설치",
    "철골세우기1": "철골 작업", "철골세우기2": "철골 작업", "철골세우기3": "철골 작업",
    "본조임": "볼트 본조임", "철골검사": "검측(감리 입회)", "바탕정리": "도장·방수",
    "방수1차": "도장·방수", "방수2차": "도장·방수",
}  # fmt: skip


def place(row: dict[str, str]) -> str:
    """동·층·구역 → '101동 9층 2구역'. 층의 F는 층으로, '전체' 구역은 뺀다."""
    floor = row["층"].replace("F", "층")
    zone = "" if row["구역"] == "전체" else row["구역"]
    return " ".join(p for p in (row["동"], floor, zone) if p)


def rows(start: date) -> list[tuple[str, ...]]:
    shift = start - REFERENCE_MONDAY
    out: list[tuple[str, ...]] = []
    with SOURCE.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            kind = KINDS[row["작업ID"].rsplit("-", 1)[1]]
            day = (date.fromisoformat(row["날짜"]) + shift).isoformat()
            begin, end = row["시작"], row["종료"]
            if (begin, end) == ("00:00", "23:59"):  # 양생: 상부 작업 통제를 낮 시간으로
                begin, end = "07:00", "17:00"
            memo = row["작업"] if row["작업"] != kind else ""
            out.append((day, begin, end, kind, place(row), row["실행업체"], memo))
            # 크레인·고소작업대를 쓰는 철골 작업은 장비 작업을 따로 둔다(날씨 판정 대상)
            if kind == "철골 작업":
                out.append((day, begin, end, "이동식 크레인", place(row), "미래크레인",
                            "50t, 철골 양중"))  # fmt: skip
            if kind == "볼트 본조임":
                out.append((day, begin, end, "고소작업대", place(row), "우진철강", "2대"))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--start", default=REFERENCE_MONDAY.isoformat(), help="첫 월요일")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    start = date.fromisoformat(args.start)
    if start.weekday() != 0:
        start -= timedelta(days=start.weekday())
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.title = "공정표"
    sheet.append(HEAD)
    for row in rows(start):
        sheet.append(row)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="DBE8FE")
        cell.alignment = Alignment(horizontal="center")
    for index, width in enumerate((12, 8, 8, 18, 22, 18, 40), start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    sheet.freeze_panes = "A2"
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    book.save(out)
    print(f"{out} · {sheet.max_row - 1}줄 · {start}부터")
    return 0


if __name__ == "__main__":
    sys.exit(main())
