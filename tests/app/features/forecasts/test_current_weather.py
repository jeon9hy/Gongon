"""홈 날씨 카드(C04-54): 지금과 가장 가까운 예보 시각 한 칸. 관측이 아니라 예보다.

conftest.FIXED_NOW = 2026-10-04 15:00(KST).
항목 이름·코드는 단기예보 활용가이드를 따르고 값은 테스트용이다.
"""

from datetime import datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.features.forecasts import service
from app.features.forecasts.models import STATUS_FAILED, STATUS_SUCCESS, ForecastRun
from app.features.sites.models import Site
from engine.kst import KST
from tests.conftest import FIXED_NOW

NX, NY = 60, 127
BASE_AT = datetime(2026, 10, 4, 14, 0, tzinfo=KST)


def item(category: str, value: str, hhmm: str) -> dict[str, Any]:
    return {
        "baseDate": "20261004", "baseTime": "1400", "category": category,
        "fcstDate": "20261004", "fcstTime": hhmm, "fcstValue": value, "nx": NX, "ny": NY,
    }  # fmt: skip


ITEMS = [
    item("TMP", "18", "1500"), item("WSD", "3.2", "1500"), item("POP", "20", "1500"),
    item("PCP", "강수없음", "1500"), item("SKY", "3", "1500"), item("PTY", "0", "1500"),
    item("TMP", "17", "1600"), item("REH", "60", "1600"), item("SKY", "4", "1600"),
    item("PTY", "1", "1600"), item("PCP", "1mm 미만", "1600"),
]  # fmt: skip


def save(session: Session, items: list[dict[str, Any]] | None, status: str = STATUS_SUCCESS,
         nx: int = NX, ny: int = NY, base_at: datetime = BASE_AT) -> None:  # fmt: skip
    session.add(ForecastRun(base_at=base_at, grid_nx=nx, grid_ny=ny, status=status,
                            failure_reason=None, raw_items=items))  # fmt: skip
    session.commit()


def test_picks_the_nearest_hour_and_leaves_missing_values_empty(session: Session) -> None:
    save(session, ITEMS)

    at_15 = service.current_weather(session, NX, NY, FIXED_NOW + timedelta(minutes=20))
    assert at_15 is not None
    assert at_15.valid_at == datetime(2026, 10, 4, 15, tzinfo=KST)
    assert (at_15.temperature_c, at_15.wind_speed_mps, at_15.rain_probability_pct) == (18, 3.2, 20)
    assert at_15.sky == "구름많음"
    assert at_15.humidity_pct is None  # 15시 습도 없음 → 채우지 않는다

    at_16 = service.current_weather(session, NX, NY, FIXED_NOW + timedelta(minutes=40))
    assert at_16 is not None
    assert at_16.valid_at == datetime(2026, 10, 4, 16, tzinfo=KST)
    assert (at_16.sky, at_16.precipitation_text) == ("비", "1mm 미만")
    assert at_16.wind_speed_mps is None and at_16.rain_probability_pct is None


def test_no_card_value_when_forecast_is_more_than_an_hour_away(session: Session) -> None:
    save(session, ITEMS)

    # 마지막 예보 시각은 16시: 17시까지는 16시 값, 17:01부터는 보이지 않는다
    assert service.current_weather(session, NX, NY, FIXED_NOW + timedelta(minutes=120)) is not None
    assert service.current_weather(session, NX, NY, FIXED_NOW + timedelta(minutes=121)) is None
    assert service.current_weather(session, NX, NY, FIXED_NOW - timedelta(minutes=61)) is None


def test_uses_the_latest_successful_run_of_that_grid_only(session: Session) -> None:
    save(session, ITEMS)
    save(session, None, STATUS_FAILED, base_at=BASE_AT + timedelta(hours=3))
    save(session, [item("TMP", "-5", "1500")], nx=NX + 1)

    current = service.current_weather(session, NX, NY, FIXED_NOW)
    assert current is not None and current.temperature_c == 18
    assert service.current_weather(session, NX + 2, NY, FIXED_NOW) is None


SITE = {
    "name": "가상A현장", "road_address": "서울 중구 세종대로 110",
    "latitude": "37.5665", "longitude": "126.9780",
    "work_start_date": "2026-10-01", "work_end_date": "2026-12-31",
}  # fmt: skip


def weather_card(page: str) -> str:
    return page.split('aria-label="지금 날씨"')[1].split("</section>")[0]


def test_home_card_shows_the_forecast_hour_and_issue_time(
    client: TestClient, session: Session
) -> None:
    client.post("/sites", data=SITE)
    assert "아직 받은 예보가 없어요" in weather_card(client.get("/").text)

    site = session.scalars(select(Site)).one()
    save(session, ITEMS, nx=site.grid_nx, ny=site.grid_ny)
    card = weather_card(client.get("/").text)

    assert "가상A현장" in card and "18°" in card and "구름많음" in card
    assert "15시 예보 · 14:00 발표" in card and "예보" in card
    assert "<dd>–</dd>" in card  # 습도 없음
