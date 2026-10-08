"""기상청 중기육상예보 수집·해석. 응답은 2026-10-08 실제 응답(data/)이고 네트워크 없이 검증한다."""

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from engine.forecast import (
    ForecastFetchError,
    fetch_mid_land,
    land_region_for,
    latest_issue_at,
    parse_mid_land,
    previous_issue_at,
)
from engine.kst import KST

DATA = Path(__file__).parent / "data"
REAL = DATA / "kma_mid_getMidLandFcst_202610080600_11B00000.json"
ISSUED = datetime(2026, 10, 8, 6, 0, tzinfo=KST)


def fake_get(body: bytes) -> Any:
    calls: list[dict[str, str]] = []

    def get(url: str, params: dict[str, str], timeout_s: float) -> bytes:
        calls.append(params)
        return body

    get.calls = calls  # type: ignore[attr-defined]
    return get


def test_real_response_maps_day_offsets_to_dates() -> None:
    item = fetch_mid_land("key", ISSUED, "11B00000", fake_get(REAL.read_bytes()))

    forecast = parse_mid_land(ISSUED, item)

    # 6시 발표는 발표일로부터 4~10일 후(활용가이드). 10/8 + 4일 = 10/12
    assert min(forecast.days) == date(2026, 10, 12)
    assert max(forecast.days) == date(2026, 10, 18)
    am, pm = forecast.days[date(2026, 10, 13)]  # 5일 후
    assert (am.part, am.weather, am.rain_probability_pct) == ("오전", "흐림", 30)
    assert (pm.part, pm.weather, pm.rain_probability_pct) == ("오후", "흐리고 비", 60)
    (whole,) = forecast.days[date(2026, 10, 16)]  # 8일 후부터는 하루 단위
    assert whole.part == "하루"


def test_request_uses_issue_time_and_region() -> None:
    get = fake_get(REAL.read_bytes())

    fetch_mid_land("key", ISSUED, "11B00000", get)

    assert get.calls[0]["tmFc"] == "202610080600"
    assert get.calls[0]["regId"] == "11B00000"


def test_18h_issue_has_no_day4_and_missing_fields_stay_missing() -> None:
    item = {"regId": "11B00000", "rnSt5Am": 20, "wf5Am": "맑음", "rnSt5Pm": "", "wf5Pm": None}

    forecast = parse_mid_land(datetime(2026, 10, 8, 18, 0, tzinfo=KST), item)

    assert list(forecast.days) == [date(2026, 10, 13)]
    am, pm = forecast.days[date(2026, 10, 13)]
    assert am.rain_probability_pct == 20
    assert (pm.rain_probability_pct, pm.weather) == (None, None)  # 빈 값을 0%·맑음으로 채우지 않음


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (
            {"response": {"header": {"resultCode": "03", "resultMsg": "NO_DATA"}}},
            "중기예보 오류 03 NO_DATA",
        ),
        (
            {
                "response": {
                    "header": {"resultCode": "00", "resultMsg": "OK"},
                    "body": {"items": {"item": []}},
                }
            },
            "중기예보 자료 없음",
        ),
    ],
)
def test_error_or_empty_response_raises(body: dict[str, Any], message: str) -> None:
    with pytest.raises(ForecastFetchError, match=message):
        fetch_mid_land("key", ISSUED, "11B00000", fake_get(json.dumps(body).encode()))


def test_missing_key_raises_without_calling() -> None:
    get = fake_get(b"")
    with pytest.raises(ForecastFetchError, match="KMA_SERVICE_KEY"):
        fetch_mid_land("", ISSUED, "11B00000", get)
    assert get.calls == []


@pytest.mark.parametrize(
    ("now", "issued"),
    [
        (datetime(2026, 10, 8, 5, 59, tzinfo=KST), datetime(2026, 10, 7, 18, 0, tzinfo=KST)),
        (datetime(2026, 10, 8, 6, 0, tzinfo=KST), datetime(2026, 10, 8, 6, 0, tzinfo=KST)),
        (datetime(2026, 10, 8, 17, 59, tzinfo=KST), datetime(2026, 10, 8, 6, 0, tzinfo=KST)),
        (datetime(2026, 10, 8, 18, 0, tzinfo=KST), datetime(2026, 10, 8, 18, 0, tzinfo=KST)),
    ],
)
def test_latest_issue_boundaries(now: datetime, issued: datetime) -> None:
    assert latest_issue_at(now) == issued
    assert previous_issue_at(issued) == issued - timedelta(hours=12)


@pytest.mark.parametrize(
    ("address", "region"),
    [
        ("서울 종로구 사직로 161", "11B00000"),
        ("경기도 수원시 팔달구", "11B00000"),
        ("세종특별자치시 한누리대로 2130", "11C20000"),
        ("전북특별자치도 전주시", "11F10000"),
        ("부산 해운대구", "11H20000"),
        ("제주특별자치도 제주시", "11G00000"),
        ("강원특별자치도 강릉시 교동", "11D20000"),  # 영동
        ("강원도 고성군", "11D20000"),
        ("강원특별자치도 평창군 대관령면", "11D10000"),  # 평창군은 영서(대관령 지점만 영동 목록)
        ("강원특별자치도 춘천시", "11D10000"),
        ("강원특별자치도", None),  # 영서·영동을 단정하지 않는다
        ("", None),
        ("Seoul", None),
    ],
)
def test_land_region_from_address(address: str, region: str | None) -> None:
    assert land_region_for(address) == region
