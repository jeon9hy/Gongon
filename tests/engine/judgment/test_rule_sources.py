"""원문 대조 완료(source_verified)로 표시한 기준표가 공식 원문 발췌와 실제로 일치하는지 검사한다.

옮겨 적을 때 생길 수 있는 오류(값·단위·이상/초과/이하/미만·조항 혼동)를 막는다. 발췌는
- 법령: scripts/fetch_law_articles.py가 국가법령정보센터 Open API 응답에서 만든다(D-026).
- KCS: scripts/fetch_kcs.py가 국가건설기준센터 OpenAPI 응답에서 만든다(D-079).
- 공식 PDF(가이드라인 등): 받은 PDF의 해시와 발췌 문장(D-033).
"""

import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from engine.judgment import Element, load_rule_set

RULES_DIR = Path(__file__).resolve().parents[3] / "rules"
VERIFIED = [
    path
    for path in sorted(RULES_DIR.glob("*.yaml"))
    if yaml.safe_load(path.read_text(encoding="utf-8")).get("source_verified") is True
]

# 원문에서 요소별 값·단위가 쓰이는 형식. {n}은 기준값. 법령은 '초당 10미터', 시행령 별표는
# '풍속 50.4km/h(14m/s)', KCS는 '5 ℃'·'5℃'·'85%'처럼 쓴다.
UNIT_PHRASES = {
    Element.WIND_SPEED_MPS: (r"초당 {n}미터", r"\({n}m/s\)"),
    Element.PRECIPITATION_MM_PER_H: (r"시간당 {n}밀리미터", r"{n}mm"),
    Element.SNOWFALL_CM_PER_H: (r"시간당 {n}센티미터",),
    Element.SENSIBLE_TEMPERATURE_C: (r"{n}도",),
    Element.TEMPERATURE_C: (r"{n} ?℃",),
    Element.HUMIDITY_PCT: (r"{n}%",),
    Element.DAILY_MEAN_TEMPERATURE_C: (r"{n} ?℃",),
    Element.MAX_TEMPERATURE_NEXT_24H_C: (r"{n} ?℃",),
    Element.MIN_TEMPERATURE_NEXT_24H_C: (r"{n} ?℃",),
}
OPERATOR_WORDS = {">=": "이상", ">": "초과", "<=": "이하", "<": "미만"}
# 기준값 0 초과(비·눈이 오면)는 원문에 숫자가 없다. 대신 그 현상을 가리키는 말이 있어야 한다.
PHENOMENON_WORDS = {
    Element.PRECIPITATION_MM_PER_H: ("비", "강우"),
    Element.SNOWFALL_CM_PER_H: ("눈", "강설", "얼어"),
}
ALL_RULES = ("steel", "heat", "concrete", "mobile_crane", "aerial_platform",
             "paint_waterproof", "asphalt_paving")  # fmt: skip


def source_texts(snapshot: dict[str, Any]) -> dict[str, str]:
    """발췌 파일 → {조항 이름: 원문}. 법령은 '제37조'·'별표 1', KCS·PDF는 '문서 번호 조항'."""
    if "law_name" in snapshot:
        assert snapshot["retrieved_from"].startswith("https://www.law.go.kr/DRF/lawService.do")
        assert re.fullmatch(r"[0-9a-f]{64}", snapshot["response_sha256"])
        return {**snapshot["articles"], **snapshot.get("appendices", {})}
    texts = {}
    for doc in snapshot["documents"]:
        digest = doc.get("response_sha256") or doc.get("pdf_sha256")
        assert re.fullmatch(r"[0-9a-f]{64}", digest or ""), doc.get("title") or doc.get("code")
        name = doc.get("code") or re.split(r"[:(]", doc["title"])[0].strip()
        for clause, text in doc["excerpts"].items():
            texts[f"{name} {clause}"] = text
    return texts


@pytest.mark.parametrize("path", sorted(RULES_DIR.glob("*.yaml")), ids=lambda p: p.name)
def test_rule_names_fit_judgment_columns(path: Path) -> None:
    # 판정 기록 열 길이(work_type·rule_version 40자, rule_source 200자)를 넘으면 저장 실패
    rules = load_rule_set(path)
    assert len(rules.work_type_label) <= 40 and len(rules.rule_version) <= 40
    assert len(rules.source) <= 200


@pytest.mark.parametrize("path", sorted(RULES_DIR.glob("*.yaml")), ids=lambda p: p.name)
def test_screen_texts_are_short(path: Path) -> None:
    # 카드·요약 줄에 그대로 붙는 문구다. 길면 판정 화면이 빽빽해진다(개발자 피드백 2026-10-17).
    for c in load_rule_set(path).conditions:
        assert c.cite and len(c.cite) <= 24, c.id
        assert c.action is None or len(c.action) <= 24, c.id


def test_every_rule_file_is_verified() -> None:
    names = {load_rule_set(path).work_type for path in VERIFIED}
    assert names == set(ALL_RULES)


@pytest.mark.parametrize("path", VERIFIED, ids=lambda p: p.name)
def test_quotes_match_official_text(path: Path) -> None:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    snapshots = data["source_snapshot"]
    texts: dict[str, str] = {}
    for name in [snapshots] if isinstance(snapshots, str) else snapshots:
        texts.update(source_texts(json.loads((RULES_DIR / name).read_text(encoding="utf-8"))))
    missing = [a for a in data["source_articles"] if a not in texts]
    assert not missing, missing
    text = "\n".join(texts[article] for article in data["source_articles"])

    for condition in load_rule_set(path).conditions:
        quote = condition.quote
        assert quote is not None and quote in text, condition.id
        if condition.threshold == 0 and condition.operator == ">":
            assert any(w in quote for w in PHENOMENON_WORDS[condition.element]), condition.id
        else:
            word = OPERATOR_WORDS[condition.operator]
            phrases = [
                p.format(n=re.escape(f"{condition.threshold:g}"))
                for p in UNIT_PHRASES[condition.element]
            ]
            pattern = rf"(?:{'|'.join(phrases)})(?:를|을|가|이)? ?{word}"
            assert re.search(pattern, quote), (condition.id, pattern)
        # 순간풍속 기준을 예보 평균풍속과 그대로 비교하면 위험을 낮춰 보게 된다(D-027).
        assert condition.forecast_lower_bound == ("순간풍속" in quote), condition.id
