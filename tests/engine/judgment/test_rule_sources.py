"""원문 대조 완료(source_verified)로 표시한 기준표가 공식 원문 발췌와 실제로 일치하는지 검사한다.

옮겨 적을 때 생길 수 있는 오류(값·단위·이상/초과·조항 혼동)를 막는다. 발췌는
scripts/fetch_law_articles.py가 국가법령정보센터 Open API 응답에서 만든다(D-026).
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

# 법령 문장에서 요소별 값·단위가 쓰이는 형식. {n}은 기준값.
UNIT_PHRASES = {
    Element.WIND_SPEED_MPS: "초당 {n}미터",
    Element.PRECIPITATION_MM_PER_H: "시간당 {n}밀리미터",
    Element.SNOWFALL_CM_PER_H: "시간당 {n}센티미터",
    Element.SENSIBLE_TEMPERATURE_C: "{n}도",
}
OPERATOR_WORDS = {">=": "이상", ">": "초과"}


@pytest.mark.parametrize("name", ["steel.yaml", "heat.yaml"])
def test_rules_with_legal_basis_are_verified(name: str) -> None:
    assert RULES_DIR / name in VERIFIED


@pytest.mark.parametrize("path", VERIFIED, ids=lambda p: p.name)
def test_quotes_match_official_article(path: Path) -> None:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    snapshot: dict[str, Any] = json.loads(
        (RULES_DIR / data["source_snapshot"]).read_text(encoding="utf-8")
    )
    assert snapshot["retrieved_from"].startswith("https://www.law.go.kr/DRF/lawService.do")
    assert re.fullmatch(r"[0-9a-f]{64}", snapshot["response_sha256"])
    assert data["source"].startswith(snapshot["law_name"])
    assert all(article in data["source"] for article in data["source_articles"])
    text = "\n".join(snapshot["articles"][article] for article in data["source_articles"])

    for condition in load_rule_set(path).conditions:
        assert condition.quote is not None and condition.quote in text, condition.id
        phrase = UNIT_PHRASES[condition.element].format(n=f"{condition.threshold:g}")
        expected = rf"{re.escape(phrase)}(?:를|을)? {OPERATOR_WORDS[condition.operator]}"
        assert re.search(expected, condition.quote), (condition.id, expected)
        # 순간풍속 기준을 예보 평균풍속과 그대로 비교하면 위험을 낮춰 보게 된다(D-027).
        assert condition.forecast_lower_bound == ("순간풍속" in condition.quote), condition.id
