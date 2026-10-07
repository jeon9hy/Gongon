from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest

from engine.judgment import Element, RuleSetError, Verdict, load_rule_set, parse_rule_set
from engine.kst import KST

STEEL_RULES = Path(__file__).resolve().parents[3] / "rules" / "steel.yaml"


def test_steel_rules_load_with_three_conditions_and_verified_source() -> None:
    rules = load_rule_set(STEEL_RULES)

    assert {c.element for c in rules.conditions} == {
        Element.WIND_SPEED_MPS,
        Element.PRECIPITATION_MM_PER_H,
        Element.SNOWFALL_CM_PER_H,
    }
    assert all(c.verdict == Verdict.STOP_REVIEW for c in rules.conditions)
    # 원문 대조 내용 자체는 test_rule_sources.py가 발췌와 비교한다.
    assert rules.source_verified is True
    assert rules.verified_on == date(2026, 10, 7)


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


def verified() -> dict[str, Any]:
    data = valid()
    data.update(
        source_verified=True,
        source_snapshot="sources/x.json",
        source_article="제1조",
        verified_on=date(2026, 10, 7),
    )
    data["conditions"][0]["quote"] = "1. 인용"
    return data


def test_verified_rules_keep_verification_date() -> None:
    assert parse_rule_set(verified()).verified_on == date(2026, 10, 7)


@pytest.mark.parametrize(
    ("key", "bad_value"),
    [
        ("verified_on", None),
        ("verified_on", "2026-10-07"),
        ("verified_on", datetime(2026, 10, 7, 9, tzinfo=KST)),
        ("source_snapshot", None),
        ("source_article", ""),
    ],
)
def test_verified_rules_without_provenance_are_rejected(key: str, bad_value: object) -> None:
    data = verified()
    data[key] = bad_value

    with pytest.raises(RuleSetError, match=key):
        parse_rule_set(data)


def test_verified_rules_require_quote_for_every_condition() -> None:
    data = verified()
    data["conditions"][0]["quote"] = None

    with pytest.raises(RuleSetError, match="c1"):
        parse_rule_set(data)


def test_verification_date_without_verified_flag_is_rejected() -> None:
    data = valid()
    data["verified_on"] = date(2026, 10, 7)

    with pytest.raises(RuleSetError, match="verified_on"):
        parse_rule_set(data)
