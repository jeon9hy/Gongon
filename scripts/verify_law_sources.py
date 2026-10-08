"""저장한 법령 발췌(rules/sources/*.json)가 지금 국가법령정보센터 원문과 같은지 실제 API로 확인한다.

사용: uv run python -m scripts.verify_law_sources
- LAW_OC(open.law.go.kr에서 신청한 인증키)가 환경 변수나 .env에 있어야 한다.
  테스트·CI는 네트워크를 쓰지 않으므로, 기준을 바꾸거나 법령 개정이 의심될 때 직접 실행한다
  (D-029).
- 두 가지를 본다. ① 목록 API(lawSearch)의 현행 시행본 MST가 발췌의 MST와 같은지
  (다르면 새 시행본이 나온 것).
  ② 발췌의 MST로 본문(lawService)을 다시 받아 조문·별표 텍스트가 발췌와 같은지.
- 기준표 quote ↔ 발췌 대조는 오프라인 테스트(tests/engine/judgment/test_rule_sources.py)가 맡는다.
- 종료 코드: 0 모두 일치, 1 차이 있음(기준 검토 필요), 2 확인 불가(OC 없음·호출 실패).
"""

import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from pathlib import Path

from app.core.config import ENV_FILE, REPO_ROOT, read_env_file
from scripts.fetch_law_articles import API_URL, extract

SEARCH_URL = "https://www.law.go.kr/DRF/lawSearch.do"
SOURCES_DIR = REPO_ROOT / "rules" / "sources"


def request_numbers(snapshot: Mapping[str, object]) -> tuple[list[str], list[str]]:
    """발췌 키("제566조의2", "별표 13의2")를 fetch_law_articles 인자("566-2", "13-2")로 바꾼다."""
    articles = [_number(key, r"제(\d+)조(?:의(\d+))?") for key in _keys(snapshot, "articles")]
    appendices = [_number(key, r"별표 (\d+)(?:의(\d+))?") for key in _keys(snapshot, "appendices")]
    return articles, appendices


def _keys(snapshot: Mapping[str, object], field: str) -> list[str]:
    value = snapshot.get(field) or {}
    assert isinstance(value, dict)
    return list(value)


def _number(key: str, pattern: str) -> str:
    match = re.fullmatch(pattern, key)
    if match is None:
        raise ValueError(f"발췌 키 형식을 알 수 없음: {key}")
    number, branch = match.groups()
    return number + (f"-{branch}" if branch else "")


def current_mst(search_xml: bytes, law_id: str) -> str | None:
    """lawSearch 응답에서 법령ID가 같은 현행 법령의 법령일련번호(MST). 없으면 None."""
    root = ET.fromstring(search_xml)
    for law in root.iter("law"):
        if law.findtext("법령ID") == law_id and law.findtext("현행연혁코드") == "현행":
            return law.findtext("법령일련번호")
    return None


def text_differences(saved: Mapping[str, object], live: Mapping[str, object]) -> list[str]:
    """발췌와 새로 받은 본문에서 텍스트가 달라진 조문·별표 이름."""
    changed: list[str] = []
    for field in ("articles", "appendices"):
        saved_texts, live_texts = saved.get(field) or {}, live.get(field) or {}
        assert isinstance(saved_texts, dict) and isinstance(live_texts, dict)
        changed += [key for key in saved_texts if saved_texts[key] != live_texts.get(key)]
    return changed


def _get(url: str, query: dict[str, str]) -> bytes:
    with urllib.request.urlopen(f"{url}?{urllib.parse.urlencode(query)}", timeout=60) as res:
        body: bytes = res.read()
    return body


def verify(path: Path, oc: str) -> list[str]:
    """한 발췌 파일의 문제 목록. 비어 있으면 원문과 일치."""
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    problems: list[str] = []
    search = {"OC": oc, "target": "law", "type": "XML", "query": str(snapshot["law_name"])}
    live_mst = current_mst(_get(SEARCH_URL, search), str(snapshot["law_id"]))
    if live_mst is None:
        problems.append("목록 API에서 현행 법령을 찾지 못함(법령명·법령ID 확인)")
    elif live_mst != snapshot["mst"]:
        problems.append(
            f"새 시행본: 현행 MST {live_mst}, 발췌 MST {snapshot['mst']} — 다시 받고 기준 검토"
        )
    articles, appendices = request_numbers(snapshot)
    body = _get(API_URL, {"OC": oc, "target": "law", "MST": str(snapshot["mst"]), "type": "XML"})
    problems += [
        f"{key} 텍스트가 발췌와 다름"
        for key in text_differences(snapshot, extract(body, articles, appendices))
    ]
    return problems


def main() -> int:
    oc = os.environ.get("LAW_OC") or read_env_file(ENV_FILE).get("LAW_OC", "")
    if not oc:
        print("LAW_OC가 없음: .env에 LAW_OC=<신청한 인증키> 추가(docs/setup.md)")
        return 2
    sources = [
        p for p in sorted(SOURCES_DIR.glob("*.json")) if "mst" in json.loads(p.read_text("utf-8"))
    ]
    status = 0
    for path in sources:
        try:
            problems = verify(path, oc)
        except (
            OSError,
            ET.ParseError,
            SystemExit,
        ) as error:  # extract()는 응답 이상을 SystemExit로 알린다
            print(f"확인 불가  {path.name}: {error}")
            status = 2
            continue
        print(("차이 있음" if problems else "일치     ") + f"  {path.name}")
        for problem in problems:
            print(f"  - {problem}")
        if problems and status == 0:
            status = 1
    return status


if __name__ == "__main__":
    sys.exit(main())
