"""작업 종류 목록(D-085)이 법령 원문 표와 맞는지, 기존 작업 이름을 잃지 않는지 검사한다.

업종·업무분야 이름은 옮겨 적을 때 'ㆍ'(가운뎃점)·괄호·순서가 틀리기 쉬워 원문 발췌의 표를 직접
읽어 대조한다. 발췌는 scripts/fetch_law_articles.py가 국가법령정보센터 Open API 응답에서 만든다.
"""

import json
import re

from app.core.config import REPO_ROOT
from app.core.rules import WORK_TYPE_LABELS
from app.core.work_kinds import WORK_KIND_NAMES, WORK_TRADES

SOURCE = REPO_ROOT / "rules" / "sources" / "construction_industry_enforcement_mst287349.json"
EXPIRED = {"시설물유지관리업"}  # 별표 1의 효력 규정: 2023-12-31까지 유효


def _specialty_table() -> list[tuple[str, tuple[str, ...]]]:
    """별표 1 제2호 표의 (업종, 업무분야들) 순서. 칸 안에서 줄바꿈된 글자는 이어 붙인다."""
    text = json.loads(SOURCE.read_text(encoding="utf-8"))["appendices"]["별표 1"]
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("2. 전문공사"))
    table: list[tuple[str, tuple[str, ...]]] = []
    trade, field, fields = "", "", []
    for line in lines[start + 1 :]:
        if not line.startswith(("┌", "│", "├", "└")):
            if table:
                break  # 표가 끝남
            continue
        cells = re.split(r"[┌┐└┘├┤┬┴┼│]", line)
        first, second = cells[1].strip(), cells[2].strip()
        if first and set(first) == {"─"}:  # 업종 칸의 가로선: 한 업종이 끝남
            if field:
                fields.append(field)
            if trade:
                table.append((trade, tuple(fields)))
            trade, field, fields = "", "", []
        elif second and set(second) == {"─"}:  # 업무분야 칸의 가로선
            fields.append(field)
            field = ""
        else:
            trade += first
            field += second
    header, *rows = table
    assert header == ("건설업종", ("업무분야",))
    return [
        (re.sub(r"^[가-힣]\. ?", "", name), tuple(re.sub(r"^\d\) ?", "", f) for f in names))
        for name, names in rows
    ]


def test_legal_trades_match_source_table() -> None:
    source = [(name, fields) for name, fields in _specialty_table() if name not in EXPIRED]
    ours = [(t.name, tuple(f.name for f in t.fields)) for t in WORK_TRADES if t.legal]
    assert ours == source
    assert len(source) == 14  # 원문 표의 전문공사 업종 수(만료 업종 제외)


def test_kind_names_keep_existing_judged_work_types() -> None:
    # 저장된 작업은 판정 공종 이름이다. 목록에서 빠지면 그 작업을 복사·다시 고를 수 없다.
    assert set(WORK_TYPE_LABELS) <= set(WORK_KIND_NAMES)


def test_kind_names_fit_column() -> None:
    assert all(0 < len(name) <= 40 for name in WORK_KIND_NAMES)  # work_items.work_type 길이
