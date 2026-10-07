"""규칙 기반 판정. 같은 입력·같은 기준이면 항상 같은 결과를 낸다(LLM·외부 호출 없음)."""

from collections.abc import Iterable
from datetime import datetime, timedelta

from engine.judgment.types import (
    ELEMENT_LABEL,
    ELEMENT_UNIT,
    Condition,
    ConditionResult,
    ForecastValue,
    HourlyForecast,
    HourResult,
    JudgmentResult,
    RuleSet,
    TimeWindow,
    Verdict,
    WeatherInput,
)

_HOUR = timedelta(hours=1)
OPERATOR_TEXT = {">=": "이상", ">": "초과"}


def judge(
    weather: WeatherInput, rule_set: RuleSet, work_start_at: datetime, work_end_at: datetime
) -> JudgmentResult:
    """작업 시간에 걸친 정시 예보마다 조건을 비교하고, 구간 판정은 가장 높은 단계로 정한다.

    예보 시각 h는 h:00~h+1:00 구간을 대표한다고 본다(D-018, 활용가이드 대조 필요).
    """
    if work_start_at.tzinfo is None or work_end_at.tzinfo is None:
        raise ValueError("작업 시각에 시간대가 없음")
    if work_start_at >= work_end_at:
        raise ValueError("작업 시작이 종료보다 늦거나 같음")

    by_time = {h.valid_at: h for h in weather.hours}
    hours = tuple(
        _judge_hour(slot, by_time.get(slot), rule_set)
        for slot in _hour_slots(work_start_at, work_end_at)
    )
    return JudgmentResult(
        work_type=rule_set.work_type,
        rule_version=rule_set.rule_version,
        forecast_issued_at=weather.forecast_issued_at,
        verdict=highest(h.verdict for h in hours),
        hours=hours,
        windows=_windows(hours, work_start_at, work_end_at),
    )


def highest(verdicts: Iterable[Verdict]) -> Verdict:
    items = list(verdicts)
    if not items:
        raise ValueError("판정할 항목이 없음")
    return max(items, key=lambda v: v.severity)


def _hour_slots(start_at: datetime, end_at: datetime) -> list[datetime]:
    slot = start_at.replace(minute=0, second=0, microsecond=0)
    slots = []
    while slot < end_at:
        slots.append(slot)
        slot += _HOUR
    return slots


def _judge_hour(slot: datetime, forecast: HourlyForecast | None, rule_set: RuleSet) -> HourResult:
    results = tuple(
        _judge_condition(c, None if forecast is None else forecast.values.get(c.element))
        for c in rule_set.conditions
    )
    verdict = highest(r.verdict for r in results)
    return HourResult(valid_at=slot, verdict=verdict, conditions=results)


def _judge_condition(condition: Condition, value: ForecastValue | None) -> ConditionResult:
    label = ELEMENT_LABEL[condition.element]
    rule_text = (
        f"{condition.threshold:g} {ELEMENT_UNIT[condition.element]} "
        f"{OPERATOR_TEXT[condition.operator]}"
    )

    def result(verdict: Verdict, reason: str) -> ConditionResult:
        return ConditionResult(
            condition_id=condition.id,
            element=condition.element,
            verdict=verdict,
            value=value,
            reason=reason,
        )

    if value is None:
        return result(Verdict.UNAVAILABLE, f"{label} 예보값 없음")
    if not condition.forecast_comparable:
        return result(Verdict.CHECK, f"{label} 기준은 예보로 직접 비교할 수 없음 · 현장 확인")

    over, below = _compare(value, condition.operator, condition.threshold)
    if over:
        action = f" · {condition.action}" if condition.action else ""
        return result(condition.verdict, f"{label} {value.raw} → 기준 {rule_text}에 해당{action}")
    if below and condition.forecast_lower_bound:  # 평균이 기준 아래여도 순간값은 넘을 수 있다
        return result(
            Verdict.CHECK,
            f"{label} {value.raw}: 예보는 평균값이라 기준 {rule_text}(순간값) 해당 여부 미상"
            " · 현장 측정 확인",
        )
    if below:
        return result(Verdict.GO, f"{label} {value.raw} → 기준 {rule_text} 미만")
    # 범주 예보가 기준값에 걸쳐 있어 넘는지 알 수 없다. 넘는다고 단정하지 않는다.
    return result(Verdict.CHECK, f"{label} {value.raw}: 예보 범주가 기준 {rule_text}에 걸쳐 있음")


def _compare(value: ForecastValue, operator: str, threshold: float) -> tuple[bool, bool]:
    """(구간 전체가 기준에 해당, 구간 전체가 기준 미해당)."""
    if operator == ">=":
        over = value.lower >= threshold
        below = value.upper is not None and (
            value.upper < threshold or (value.upper == threshold and not value.upper_inclusive)
        )
    elif operator == ">":
        over = value.lower > threshold
        below = value.upper is not None and value.upper <= threshold
    else:
        raise ValueError(f"지원하지 않는 연산 {operator!r}")
    return over, below


def _windows(
    hours: tuple[HourResult, ...], start_at: datetime, end_at: datetime
) -> tuple[TimeWindow, ...]:
    windows: list[TimeWindow] = []
    for hour in hours:
        slot_start = max(hour.valid_at, start_at)
        slot_end = min(hour.valid_at + _HOUR, end_at)
        if windows and windows[-1].verdict == hour.verdict:
            windows[-1] = TimeWindow(windows[-1].start_at, slot_end, hour.verdict)
        else:
            windows.append(TimeWindow(slot_start, slot_end, hour.verdict))
    return tuple(windows)
