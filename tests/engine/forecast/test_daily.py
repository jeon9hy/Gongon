"""하루 단위 기온(KCS 14 20 41 일평균기온 정의·타설 후 24시간 최고) 계산."""

from datetime import datetime, timedelta

from engine.forecast import with_daily_temperatures
from engine.judgment import Element, ForecastValue, HourlyForecast, WeatherInput
from engine.kst import KST

DAY = datetime(2026, 10, 5, tzinfo=KST)
MEAN = Element.DAILY_MEAN_TEMPERATURE_C
PEAK = Element.MAX_TEMPERATURE_NEXT_24H_C


def weather(temps: dict[datetime, float]) -> WeatherInput:
    return WeatherInput(
        DAY - timedelta(hours=7),
        tuple(
            HourlyForecast(t, {Element.TEMPERATURE_C: ForecastValue.exact(v, f"{v}")})
            for t, v in sorted(temps.items())
        ),
    )


def hours(start: datetime, count: int, value: float = 20.0) -> dict[datetime, float]:
    return {start + timedelta(hours=i): value for i in range(count)}


def values_at(w: WeatherInput, hour: int) -> dict[Element, ForecastValue]:
    return next(h.values for h in w.hours if h.valid_at == DAY.replace(hour=hour))


def test_daily_mean_uses_eight_kcs_hours_including_next_midnight() -> None:
    temps = hours(DAY, 48, 0.0)
    for i, h in enumerate((3, 6, 9, 12, 15, 18, 21, 24)):
        temps[DAY + timedelta(hours=h)] = float(i)  # 0..7 → 평균 3.5
    temps[DAY + timedelta(hours=10)] = 99.0  # 8회 시각이 아니면 평균에 들지 않는다
    result = with_daily_temperatures(weather(temps), DAY.replace(hour=9), DAY.replace(hour=11))
    assert values_at(result, 9)[MEAN].lower == 3.5
    assert values_at(result, 10)[MEAN].lower == 3.5


def test_missing_midnight_means_no_daily_mean() -> None:
    temps = hours(DAY, 24)  # 다음 날 00시(=24시) 없음
    result = with_daily_temperatures(weather(temps), DAY.replace(hour=9), DAY.replace(hour=10))
    assert MEAN not in values_at(result, 9)


def test_peak_is_max_of_24_hours_after_work_end() -> None:
    temps = hours(DAY, 48)
    temps[DAY.replace(hour=17)] = 40.0  # 종료 시각 자체는 '이후'가 아니다
    temps[DAY + timedelta(hours=17 + 24)] = 31.0  # 종료 + 24시간은 포함
    result = with_daily_temperatures(weather(temps), DAY.replace(hour=9), DAY.replace(hour=17))
    assert values_at(result, 9)[PEAK].lower == 31.0


def test_missing_hour_in_next_24h_means_no_peak() -> None:
    temps = hours(DAY, 48)
    del temps[DAY + timedelta(hours=30)]
    result = with_daily_temperatures(weather(temps), DAY.replace(hour=9), DAY.replace(hour=17))
    assert PEAK not in values_at(result, 9)


def test_values_are_added_only_to_work_hours() -> None:
    result = with_daily_temperatures(weather(hours(DAY, 48)), DAY.replace(hour=9),
                                     DAY.replace(hour=11))  # fmt: skip
    assert MEAN in values_at(result, 10)
    assert MEAN not in values_at(result, 11)
