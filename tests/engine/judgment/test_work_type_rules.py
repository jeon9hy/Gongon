"""D-080 기준표(크레인·고소작업대·도장·방수·아스팔트 포장)의 경계값이 원문대로 동작하는지.

원문 '이상/초과/이하/미만'을 바로 아래·같음·위 값으로 확인한다. 인용 일치는 test_rule_sources.py.
"""

from datetime import datetime
from pathlib import Path

import pytest

from engine.judgment import (
    Element,
    ForecastValue,
    HourlyForecast,
    Verdict,
    WeatherInput,
    judge,
    load_rule_set,
)
from engine.kst import KST

RULES_DIR = Path(__file__).resolve().parents[3] / "rules"
DAY = datetime(2026, 10, 5, tzinfo=KST)
CALM = {
    Element.WIND_SPEED_MPS: ForecastValue.exact(3.0, "3"),
    Element.PRECIPITATION_MM_PER_H: ForecastValue.exact(0.0, "강수없음"),
    Element.SNOWFALL_CM_PER_H: ForecastValue.exact(0.0, "적설없음"),
    Element.TEMPERATURE_C: ForecastValue.exact(15.0, "15"),
    Element.HUMIDITY_PCT: ForecastValue.exact(60.0, "60"),
}


def verdict(rule_file: str, **changes: float) -> Verdict:
    values = {**CALM, **{Element(k): ForecastValue.exact(v, f"{v}") for k, v in changes.items()}}
    w = WeatherInput(DAY, tuple(HourlyForecast(DAY.replace(hour=h), values) for h in (9, 10)))
    rules = load_rule_set(RULES_DIR / rule_file)
    return judge(w, rules, DAY.replace(hour=9), DAY.replace(hour=10)).verdict


@pytest.mark.parametrize("rule_file", ["mobile_crane.yaml", "aerial_platform.yaml"])
@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({}, Verdict.GO),
        ({"wind_speed_mps": 13.9}, Verdict.GO),
        ({"wind_speed_mps": 14.0}, Verdict.STOP_REVIEW),  # 강풍주의보 '14m/s 이상'
        ({"precipitation_mm_per_h": 0.5}, Verdict.CHECK),  # 제37조①: 수치 없음 → 현장 판단
        ({"snowfall_cm_per_h": 0.5}, Verdict.CHECK),
    ],
)
def test_lifting_and_aerial_work(
    rule_file: str, changes: dict[str, float], expected: Verdict
) -> None:
    assert verdict(rule_file, **changes) == expected


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({}, Verdict.GO),
        ({"temperature_c": 5.0}, Verdict.GO),  # '5 ℃ 미만'
        ({"temperature_c": 4.9}, Verdict.STOP_REVIEW),
        ({"humidity_pct": 85.0}, Verdict.GO),  # '85%를 초과'
        ({"humidity_pct": 86.0}, Verdict.STOP_REVIEW),
        ({"precipitation_mm_per_h": 0.5}, Verdict.STOP_REVIEW),  # 눈·비가 올 때
        ({"snowfall_cm_per_h": 0.5}, Verdict.STOP_REVIEW),
    ],
)
def test_paint_waterproof(changes: dict[str, float], expected: Verdict) -> None:
    assert verdict("paint_waterproof.yaml", **changes) == expected


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({}, Verdict.GO),
        ({"temperature_c": 5.1}, Verdict.GO),
        ({"temperature_c": 5.0}, Verdict.STOP_REVIEW),  # '5℃ 이하'
        ({"precipitation_mm_per_h": 0.5}, Verdict.STOP_REVIEW),
        ({"snowfall_cm_per_h": 0.5}, Verdict.CHECK),  # 표면 동결·습윤은 현장 확인
    ],
)
def test_asphalt_paving(changes: dict[str, float], expected: Verdict) -> None:
    assert verdict("asphalt_paving.yaml", **changes) == expected


def test_missing_humidity_is_unavailable_not_go() -> None:
    values: dict[Element, ForecastValue] = {
        k: v for k, v in CALM.items() if k != Element.HUMIDITY_PCT
    }
    w = WeatherInput(DAY, tuple(HourlyForecast(DAY.replace(hour=h), values) for h in (9, 10)))
    rules = load_rule_set(RULES_DIR / "paint_waterproof.yaml")
    assert judge(w, rules, DAY.replace(hour=9), DAY.replace(hour=10)).verdict == Verdict.UNAVAILABLE
