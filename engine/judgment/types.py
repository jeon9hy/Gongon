"""판정 엔진의 입력·출력 타입. 예보 수집(engine/forecast)도 이 입력 타입으로 변환해 넘긴다."""

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum


class Verdict(StrEnum):
    GO = "진행"
    CHECK = "확인 필요"
    UNAVAILABLE = "판정 불가"
    STOP_REVIEW = "중지 검토"

    @property
    def severity(self) -> int:
        # 구간 판정은 가장 높은 단계(D-018). 판정 불가는 '진행'이라고 말할 수 없으므로
        # 확인 필요보다 높고, 기준을 넘은 시각이 있으면 중지 검토가 우선한다.
        return _SEVERITY[self]


_SEVERITY = {Verdict.GO: 0, Verdict.CHECK: 1, Verdict.UNAVAILABLE: 2, Verdict.STOP_REVIEW: 3}


class Element(StrEnum):
    WIND_SPEED_MPS = "wind_speed_mps"
    PRECIPITATION_MM_PER_H = "precipitation_mm_per_h"
    SNOWFALL_CM_PER_H = "snowfall_cm_per_h"
    TEMPERATURE_C = "temperature_c"
    HUMIDITY_PCT = "humidity_pct"
    # 기온·습도로 계산한 값(engine/forecast/sensible.py). 둘 중 하나라도 없으면 만들지 않는다.
    SENSIBLE_TEMPERATURE_C = "sensible_temperature_c"
    # 하루 단위 값(engine/forecast/daily.py). 작업 시간의 모든 시각에 같은 값으로 넣는다.
    DAILY_MEAN_TEMPERATURE_C = "daily_mean_temperature_c"  # KCS 정의: 03~24시 3시간 간격 8회 평균
    MAX_TEMPERATURE_NEXT_24H_C = "max_temperature_next_24h_c"  # 작업 종료 후 24시간 최고


ELEMENT_LABEL = {
    Element.WIND_SPEED_MPS: "풍속",
    Element.PRECIPITATION_MM_PER_H: "강우",
    Element.SNOWFALL_CM_PER_H: "강설",
    Element.TEMPERATURE_C: "기온",
    Element.HUMIDITY_PCT: "습도",
    Element.SENSIBLE_TEMPERATURE_C: "체감온도",
    Element.DAILY_MEAN_TEMPERATURE_C: "일평균기온",
    Element.MAX_TEMPERATURE_NEXT_24H_C: "종료 후 24시간 최고기온",
}
ELEMENT_UNIT = {
    Element.WIND_SPEED_MPS: "m/s",
    Element.PRECIPITATION_MM_PER_H: "mm/h",
    Element.SNOWFALL_CM_PER_H: "cm/h",
    Element.TEMPERATURE_C: "°C",
    Element.HUMIDITY_PCT: "%",
    Element.SENSIBLE_TEMPERATURE_C: "°C",
    Element.DAILY_MEAN_TEMPERATURE_C: "°C",
    Element.MAX_TEMPERATURE_NEXT_24H_C: "°C",
}


@dataclass(frozen=True, slots=True)
class ForecastValue:
    """예보값 하나. 기상청은 강수·적설을 범주("1mm 미만", "30.0~50.0mm")로도 주므로 구간으로 담는다.

    정확한 값은 lower == upper, upper_inclusive=True.
    upper가 None이면 위로 열린 구간("50.0mm 이상").
    """

    lower: float
    upper: float | None
    upper_inclusive: bool
    raw: str

    @classmethod
    def exact(cls, value: float, raw: str) -> "ForecastValue":
        return cls(value, value, True, raw)


@dataclass(frozen=True, slots=True)
class HourlyForecast:
    valid_at: datetime  # 예보 대상 정시(시간대 포함)
    # 요소가 없으면 누락이다. 누락은 정상값으로 채우지 않고 판정 불가로 처리한다.
    values: dict[Element, ForecastValue]


@dataclass(frozen=True, slots=True)
class WeatherInput:
    forecast_issued_at: datetime
    hours: tuple[HourlyForecast, ...]


@dataclass(frozen=True, slots=True)
class Condition:
    id: str
    element: Element
    operator: str  # ">=" 이상 / ">" 초과
    threshold: float
    verdict: Verdict  # 기준을 넘었을 때의 판정
    forecast_comparable: bool
    quote: str | None
    # 예보값이 기준 대상 양의 하한일 때(예: 평균풍속 ≤ 순간풍속).
    # 예보값이 기준을 넘으면 대상도 넘지만, 넘지 않으면 대상이 넘는지 알 수 없다.
    forecast_lower_bound: bool = False
    action: str | None = None  # 기준에 해당할 때 법령이 요구하는 조치(사유에 덧붙인다)


@dataclass(frozen=True, slots=True)
class RuleSet:
    work_type: str
    work_type_label: str
    rule_version: str
    source: str
    source_verified: bool
    conditions: tuple[Condition, ...]
    verified_on: date | None = None  # 원문 대조일. source_verified일 때만 있다


@dataclass(frozen=True, slots=True)
class ConditionResult:
    condition_id: str
    element: Element
    verdict: Verdict
    value: ForecastValue | None  # 누락이면 None
    reason: str  # 계산식 또는 판정 불가·확인 필요 사유


@dataclass(frozen=True, slots=True)
class HourResult:
    valid_at: datetime
    verdict: Verdict
    conditions: tuple[ConditionResult, ...]


@dataclass(frozen=True, slots=True)
class TimeWindow:
    start_at: datetime
    end_at: datetime
    verdict: Verdict


@dataclass(frozen=True, slots=True)
class JudgmentResult:
    work_type: str
    rule_version: str
    forecast_issued_at: datetime
    verdict: Verdict
    hours: tuple[HourResult, ...]
    windows: tuple[TimeWindow, ...]
