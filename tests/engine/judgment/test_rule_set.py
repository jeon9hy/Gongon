from pathlib import Path
from typing import Any

import pytest

from engine.judgment import Element, RuleSetError, Verdict, load_rule_set, parse_rule_set

STEEL_RULES = Path(__file__).resolve().parents[3] / "rules" / "steel.yaml"


def test_steel_rules_load_with_three_conditions_and_unverified_source() -> None:
    rules = load_rule_set(STEEL_RULES)

    assert {c.element for c in rules.conditions} == {
        Element.WIND_SPEED_MPS,
        Element.PRECIPITATION_MM_PER_H,
        Element.SNOWFALL_CM_PER_H,
    }
    assert all(c.verdict == Verdict.STOP_REVIEW for c in rules.conditions)
    # 원문 대조 전에는 검증 완료로 표시하지 않는다.
    assert rules.source_verified is False


def valid() -> dict[str, Any]:
    return {
        "work_type": "steel",
        "work_type_label": "철골 작업",
        "rule_version": "v1",
        "source": "근거",
        "source_verified": False,
        "conditions": [
            {
                "id": "c1",
                "element": "precipitation_mm_per_h",
                "operator": ">=",
                "threshold": 1.0,
                "verdict": "중지 검토",
                "forecast_comparable": True,
                "quote": None,
            }
        ],
    }


@pytest.mark.parametrize(
    ("key", "bad_value"),
    [
        ("operator", "=>"),
        ("threshold", "1.0"),
        ("threshold", True),
        ("element", "temperature"),
        ("verdict", "중지"),
        ("forecast_comparable", "yes"),
    ],
)
def test_malformed_condition_is_rejected(key: str, bad_value: object) -> None:
    data = valid()
    data["conditions"][0][key] = bad_value

    with pytest.raises(RuleSetError):
        parse_rule_set(data)


def test_missing_rule_version_is_rejected() -> None:
    data = valid()
    del data["rule_version"]

    with pytest.raises(RuleSetError, match="rule_version"):
        parse_rule_set(data)
