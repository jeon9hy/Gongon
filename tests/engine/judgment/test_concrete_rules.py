"""rules/concrete.yaml의 경계값이 출처 문장(가이드라인·KCS 14 20 41·40)대로 동작하는지 검사한다.

인용이 원문과 같은지는 test_rule_sources.py가 검사한다.
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
RULES = load_rule_set(RULES_DIR / "concrete.yaml")
DAY = datetime(2026, 10, 5, tzinfo=KST)
MILD = {
    Element.PRECIPITATION_MM_PER_H: ForecastValue.exact(0.0, "강수없음"),
    Element.DAILY_MEAN_TEMPERATURE_C: ForecastValue.exact(15.0, "15.0"),
    Element.MAX_TEMPERATURE_NEXT_24H_C: ForecastValue.exact(20.0, "20"),
    Element.MIN_TEMPERATURE_NEXT_24H_C: ForecastValue.exact(8.0, "8"),
}


def verdict(**changes: ForecastValue) -> Verdict:
    values = {**MILD, **{Element(k): v for k, v in changes.items()}}
    # 같은 날씨가 다음 시각까지 이어진다(누적값 두 해석, D-030).
    w = WeatherInput(DAY, tuple(HourlyForecast(DAY.replace(hour=h), values) for h in (9, 10)))
    return judge(w, RULES, DAY.replace(hour=9), DAY.replace(hour=10)).verdict


def exact(v: float) -> ForecastValue:
    return ForecastValue.exact(v, f"{v}")


def test_mild_dry_day_is_go() -> None:
    assert verdict() == Verdict.GO


@pytest.mark.parametrize(
    ("rain", "expected"),
    [
        (ForecastValue(0.0, 1.0, False, "1mm 미만"), Verdict.CHECK),  # 비가 오면 원칙 금지
        (exact(3.0), Verdict.CHECK),  # 3mm 이하: 부득이 시 가이드라인 조치
        (exact(3.1), Verdict.STOP_REVIEW),  # 3mm 초과: 즉시 중지
    ],
)
def test_rain_thresholds(rain: ForecastValue, expected: Verdict) -> None:
    assert verdict(precipitation_mm_per_h=rain) == expected


@pytest.mark.parametrize(
    ("mean", "peak", "expected"),
    [
        (25.0, 30.0, Verdict.GO),  # 둘 다 '초과'가 아님
        (25.1, 20.0, Verdict.CHECK),
        (20.0, 30.1, Verdict.CHECK),
        (4.1, 10.0, Verdict.GO),
        (4.0, 10.0, Verdict.CHECK),  # 한중: 일평균기온 4 ℃ 이하(KCS 14 20 40 1.1(2))
    ],
)
def test_temperature_thresholds(mean: float, peak: float, expected: Verdict) -> None:
    got = verdict(daily_mean_temperature_c=exact(mean), max_temperature_next_24h_c=exact(peak))
    assert got == expected


def test_missing_daily_mean_is_unavailable_not_go() -> None:
    values: dict[Element, ForecastValue] = {
        k: v for k, v in MILD.items() if k != Element.DAILY_MEAN_TEMPERATURE_C
    }
    w = WeatherInput(DAY, tuple(HourlyForecast(DAY.replace(hour=h), values) for h in (9, 10)))
    assert judge(w, RULES, DAY.replace(hour=9), DAY.replace(hour=10)).verdict == Verdict.UNAVAILABLE


@pytest.mark.parametrize(("low", "expected"), [(0.1, Verdict.GO), (0.0, Verdict.CHECK)])
def test_cold_after_placing_uses_next_24h_minimum(low: float, expected: Verdict) -> None:
    # 한중: 타설 완료 후 24시간 동안 일최저기온 0 ℃ '이하'(KCS 14 20 40 1.1(2))
    assert verdict(min_temperature_next_24h_c=exact(low)) == expected


def test_concrete_rules_are_verified_against_all_three_sources() -> None:
    assert RULES.source_verified is True
    assert "KCS 14 20 40" in RULES.source and "KCS 14 20 41" in RULES.source
