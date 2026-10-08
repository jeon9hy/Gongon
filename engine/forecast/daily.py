"""시간별 예보 → 하루 단위 기온(콘크리트 기준용).

- 일평균기온: KCS 14 20 41:2025 1.3의 정의대로 하루(00~24시) 중 03·06·09·12·15·18·21·24시
  8개 값을 평균한다. 24시는 다음 날 00시 예보다. 관측 정의를 예보 기온(TMP)에 적용한 추정값이다.
- 작업 종료 후 24시간 최고기온: KCS 14 20 41 "타설 완료 후 24시간 이내에 일 최고기온" 비교용.
  작업 종료 시각을 타설 완료로 보고 (종료, 종료+24시간] 정시 기온의 최댓값을 쓴다.
- 필요한 시각이 하나라도 없으면 값을 만들지 않는다(판정 불가). 누락을 다른 값으로 채우지 않는다.
- 값은 작업 시간에 걸친 정시마다 같은 값으로 넣어, 시간별 판정 엔진이 그대로 비교하게 한다.
"""

from dataclasses import replace
from datetime import datetime, time, timedelta

from engine.judgment.types import Element, ForecastValue, WeatherInput

_HOUR = timedelta(hours=1)
MEAN_HOURS = (3, 6, 9, 12, 15, 18, 21, 24)


def with_daily_temperatures(
    weather: WeatherInput, work_start_at: datetime, work_end_at: datetime
) -> WeatherInput:
    temperature = {
        h.valid_at: h.values[Element.TEMPERATURE_C]
        for h in weather.hours
        if Element.TEMPERATURE_C in h.values
    }
    extra: dict[Element, ForecastValue] = {}
    mean = daily_mean_c(temperature, work_start_at)
    if mean is not None:
        extra[Element.DAILY_MEAN_TEMPERATURE_C] = mean
    peak = max_next_24h_c(temperature, work_end_at)
    if peak is not None:
        extra[Element.MAX_TEMPERATURE_NEXT_24H_C] = peak
    if not extra:
        return weather

    slot = work_start_at.replace(minute=0, second=0, microsecond=0)
    work_slots = set()
    while slot < work_end_at:
        work_slots.add(slot)
        slot += _HOUR
    hours = tuple(
        replace(h, values={**h.values, **extra}) if h.valid_at in work_slots else h
        for h in weather.hours
    )
    return replace(weather, hours=hours)


def daily_mean_c(
    temperature: dict[datetime, ForecastValue], day_at: datetime
) -> ForecastValue | None:
    midnight = datetime.combine(day_at.date(), time(0), day_at.tzinfo)
    values = [temperature.get(midnight + timedelta(hours=h)) for h in MEAN_HOURS]
    if any(v is None for v in values):
        return None
    numbers = [v.lower for v in values if v is not None]
    mean = round(sum(numbers) / len(numbers), 1)
    return ForecastValue.exact(mean, f"{mean:.1f}(03~24시 8회 평균)")


def max_next_24h_c(
    temperature: dict[datetime, ForecastValue], work_end_at: datetime
) -> ForecastValue | None:
    first = work_end_at.replace(minute=0, second=0, microsecond=0) + _HOUR
    values = [temperature.get(first + timedelta(hours=i)) for i in range(24)]
    if any(v is None for v in values):
        return None
    peak = max(v.lower for v in values if v is not None)
    return ForecastValue.exact(peak, f"{peak:g}(종료 후 24시간 최고)")
