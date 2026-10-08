from datetime import datetime, timedelta

import pytest

from engine.judgment import (
    Condition,
    Element,
    ForecastValue,
    HourlyForecast,
    RuleSet,
    Verdict,
    WeatherInput,
    judge,
)
from engine.kst import KST

ISSUED_AT = datetime(2026, 10, 4, 14, 0, tzinfo=KST)
DAY = datetime(2026, 10, 5, tzinfo=KST)
RAIN = Element.PRECIPITATION_MM_PER_H
WIND = Element.WIND_SPEED_MPS


def rule_set(*conditions: Condition) -> RuleSet:
    return RuleSet("steel", "철골 작업", "v-test", "테스트 기준", False, conditions)


def condition(
    element: Element = RAIN, operator: str = ">=", threshold: float = 1.0, comparable: bool = True
) -> Condition:
    return Condition("c", element, operator, threshold, Verdict.STOP_REVIEW, comparable, None)


def exact(value: float) -> ForecastValue:
    return ForecastValue.exact(value, f"{value}")


def weather(values_by_hour: dict[int, dict[Element, ForecastValue]]) -> WeatherInput:
    return WeatherInput(
        ISSUED_AT,
        tuple(HourlyForecast(DAY.replace(hour=h), values) for h, values in values_by_hour.items()),
    )


def judge_one(value: ForecastValue, cond: Condition) -> Verdict:
    # 같은 값이 다음 시각까지 이어지는 날씨: 누적값의 두 시각 해석(D-030)이 같은 결과를 낸다.
    steady = {9: {cond.element: value}, 10: {cond.element: value}}
    result = judge(weather(steady), rule_set(cond), DAY.replace(hour=9), DAY.replace(hour=10))
    return result.verdict


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0.9, Verdict.GO), (1.0, Verdict.STOP_REVIEW), (1.1, Verdict.STOP_REVIEW)],
)
def test_at_or_above_threshold_boundary(value: float, expected: Verdict) -> None:
    assert judge_one(exact(value), condition(operator=">=")) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0.9, Verdict.GO), (1.0, Verdict.GO), (1.1, Verdict.STOP_REVIEW)],
)
def test_strictly_above_threshold_boundary(value: float, expected: Verdict) -> None:
    assert judge_one(exact(value), condition(operator=">")) == expected


# 타워크레인: 법령은 순간풍속 15 m/s 초과, 예보는 평균풍속(순간풍속의 하한).
GUST = Condition("g", WIND, ">", 15.0, Verdict.STOP_REVIEW, True, None, forecast_lower_bound=True)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(3.0, Verdict.CHECK), (15.0, Verdict.CHECK), (15.1, Verdict.STOP_REVIEW)],
)
def test_lower_bound_forecast_never_says_go(value: float, expected: Verdict) -> None:
    # 평균이 기준 아래여도 순간풍속은 넘을 수 있으므로 '진행'이라고 하지 않는다.
    assert judge_one(exact(value), GUST) == expected


def test_lower_bound_forecast_missing_is_unavailable() -> None:
    result = judge(weather({9: {}}), rule_set(GUST), DAY.replace(hour=9), DAY.replace(hour=10))

    assert result.verdict == Verdict.UNAVAILABLE


def test_action_is_added_only_when_condition_applies() -> None:
    cond = Condition("h", RAIN, ">=", 1.0, Verdict.CHECK, True, None, action="휴식 부여")

    def reason(value: float) -> str:
        steady = {9: {RAIN: exact(value)}, 10: {RAIN: exact(value)}}
        result = judge(weather(steady), rule_set(cond), DAY.replace(hour=9), DAY.replace(hour=10))
        return result.hours[0].conditions[0].reason

    assert reason(1.0).endswith("에 해당 · 휴식 부여")
    assert "휴식 부여" not in reason(0.9)


def test_category_entirely_below_threshold_is_go() -> None:
    # 기상청 "1mm 미만" = [0, 1.0). 기준 1.0 이상에 해당하는 값이 없다.
    assert judge_one(ForecastValue(0.0, 1.0, False, "1mm 미만"), condition()) == Verdict.GO


def test_category_entirely_above_threshold_is_stop_review() -> None:
    value = ForecastValue(30.0, 50.0, False, "30.0~50.0mm")
    assert judge_one(value, condition()) == Verdict.STOP_REVIEW


def test_open_ended_category_above_threshold_is_stop_review() -> None:
    assert judge_one(ForecastValue(50.0, None, False, "50.0mm 이상"), condition()) == (
        Verdict.STOP_REVIEW
    )


def test_category_straddling_threshold_needs_check_not_stop() -> None:
    value = ForecastValue(0.5, 2.0, False, "0.5~2.0mm")
    assert judge_one(value, condition()) == Verdict.CHECK


def test_condition_not_comparable_with_forecast_never_escalates_to_stop() -> None:
    assert judge_one(exact(30.0), condition(comparable=False)) == Verdict.CHECK


def test_missing_element_is_unavailable_not_filled_as_normal() -> None:
    result = judge(weather({9: {WIND: exact(3.0)}}), rule_set(condition(RAIN)),
                   DAY.replace(hour=9), DAY.replace(hour=10))  # fmt: skip

    assert result.verdict == Verdict.UNAVAILABLE
    assert result.hours[0].conditions[0].value is None


def test_missing_hour_in_work_range_is_unavailable() -> None:
    result = judge(weather({9: {RAIN: exact(0.0)}}), rule_set(condition()),
                   DAY.replace(hour=9), DAY.replace(hour=11))  # fmt: skip

    # 9시 칸은 10시 예보(h-1~h 해석)를 알 수 없어 '진행'이라고 하지 않는다(D-030).
    assert [h.verdict for h in result.hours] == [Verdict.CHECK, Verdict.UNAVAILABLE]
    assert result.verdict == Verdict.UNAVAILABLE


def test_stop_review_outranks_unavailable_and_windows_merge_same_verdicts() -> None:
    values = {
        7: {RAIN: exact(0.0)},
        8: {RAIN: exact(0.0)},
        9: {RAIN: exact(0.0)},
        10: {RAIN: exact(2.0)},
        11: {RAIN: exact(1.5)},
        12: {RAIN: exact(1.2)},
    }  # 13시 예보 없음
    result = judge(weather(values), rule_set(condition()), DAY.replace(hour=7),
                   DAY.replace(hour=14))  # fmt: skip

    assert result.verdict == Verdict.STOP_REVIEW
    # 9시·12시 칸은 두 시각 해석(D-030)의 결과가 달라 확인 필요
    assert [(w.start_at.hour, w.end_at.hour, w.verdict) for w in result.windows] == [
        (7, 9, Verdict.GO),
        (9, 10, Verdict.CHECK),
        (10, 12, Verdict.STOP_REVIEW),
        (12, 13, Verdict.CHECK),
        (13, 14, Verdict.UNAVAILABLE),
    ]


def test_partial_hour_work_time_is_clipped_to_work_range() -> None:
    values = {7: {RAIN: exact(0.0)}, 8: {RAIN: exact(0.0)}}
    start = DAY.replace(hour=7, minute=30)
    result = judge(weather(values), rule_set(condition()), start, start + timedelta(hours=1))

    assert [h.valid_at.hour for h in result.hours] == [7, 8]
    assert result.windows[0].start_at == start
    assert result.windows[-1].end_at == start + timedelta(hours=1)


def test_hourly_verdict_is_highest_condition() -> None:
    conds = (condition(RAIN), condition(WIND, threshold=10.0))
    values = {9: {RAIN: exact(0.0), WIND: exact(10.0)}, 10: {RAIN: exact(0.0)}}
    result = judge(weather(values), rule_set(*conds), DAY.replace(hour=9), DAY.replace(hour=10))

    assert [c.verdict for c in result.hours[0].conditions] == [Verdict.GO, Verdict.STOP_REVIEW]
    assert result.verdict == Verdict.STOP_REVIEW


def test_same_input_gives_same_result() -> None:
    w = weather({9: {RAIN: exact(1.0)}})
    args = (w, rule_set(condition()), DAY.replace(hour=9), DAY.replace(hour=10))

    assert judge(*args) == judge(*args)


def test_naive_work_time_is_rejected() -> None:
    naive = datetime(2026, 10, 5, 9)  # noqa: DTZ001 - 시간대 없는 입력을 거부하는지 확인
    with pytest.raises(ValueError, match="시간대"):
        judge(weather({}), rule_set(condition()), naive, naive + timedelta(hours=1))


# D-030: 누적값(강수량·적설)의 예보 시각 h가 h-1~h인지 h~h+1인지 공식 정의가 없다.
def nine_to_ten(values: dict[int, dict[Element, ForecastValue]], cond: Condition) -> Verdict:
    result = judge(weather(values), rule_set(cond), DAY.replace(hour=9), DAY.replace(hour=10))
    return result.hours[0].verdict


def test_rain_only_in_next_hour_forecast_is_check_not_go() -> None:
    result = judge(weather({9: {RAIN: exact(0.0)}, 10: {RAIN: exact(2.0)}}),
                   rule_set(condition()), DAY.replace(hour=9), DAY.replace(hour=10))  # fmt: skip
    hour = result.hours[0]
    assert hour.verdict == Verdict.CHECK
    assert "10:00 예보는 중지 검토" in hour.conditions[0].reason


def test_rain_only_in_same_hour_forecast_is_check_not_stop() -> None:
    assert (
        nine_to_ten({9: {RAIN: exact(2.0)}, 10: {RAIN: exact(0.0)}}, condition()) == Verdict.CHECK
    )


def test_missing_same_hour_is_not_filled_by_next_hour() -> None:
    assert nine_to_ten({9: {}, 10: {RAIN: exact(0.0)}}, condition()) == Verdict.UNAVAILABLE


def test_instant_element_uses_only_same_hour() -> None:
    wind = condition(WIND, threshold=10.0)
    assert (
        nine_to_ten({9: {WIND: exact(12.0)}, 10: {WIND: exact(0.0)}}, wind) == Verdict.STOP_REVIEW
    )
    assert nine_to_ten({9: {WIND: exact(0.0)}}, wind) == Verdict.GO
