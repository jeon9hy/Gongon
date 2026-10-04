"""기상청 단기예보 수집·정규화. 실제 네트워크 없이 가짜 http_get으로 검증한다.

응답 본문은 공식 활용가이드의 응답 구조(response.header/body.items.item, 항목 필드 이름)를 따르고
값은 테스트용이다. 실제 응답과의 대조는 키 발급 후 한다(docs/plan.md S02-2).
"""

import io
import json
import urllib.error
from datetime import datetime
from email.message import Message
from typing import Any

import pytest

from engine.forecast import (
    API_HUB,
    DATA_GO_KR,
    ForecastFetchError,
    KmaAuth,
    fetch_vilage_forecast,
    latest_base_at,
    normalize,
)
from engine.judgment import Element, ForecastValue
from engine.kst import KST

BASE_AT = datetime(2026, 10, 4, 14, 0, tzinfo=KST)
AUTH = KmaAuth(DATA_GO_KR, "key")


def item(category: str, value: str, fcst_time: str = "0900") -> dict[str, Any]:
    return {
        "baseDate": "20261004",
        "baseTime": "1400",
        "category": category,
        "fcstDate": "20261005",
        "fcstTime": fcst_time,
        "fcstValue": value,
        "nx": 60,
        "ny": 127,
    }


def page(items: list[dict[str, Any]], total: int, code: str = "00") -> bytes:
    body = {
        "response": {
            "header": {"resultCode": code, "resultMsg": "NORMAL_SERVICE" if code == "00" else "E"},
            "body": {
                "dataType": "JSON",
                "items": {"item": items},
                "pageNo": 1,
                "numOfRows": 1000,
                "totalCount": total,
            },
        }
    }
    return json.dumps(body, ensure_ascii=False).encode("utf-8")


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 10, 4, 14, 9, tzinfo=KST), datetime(2026, 10, 4, 11, 0, tzinfo=KST)),
        (datetime(2026, 10, 4, 14, 10, tzinfo=KST), datetime(2026, 10, 4, 14, 0, tzinfo=KST)),
        (datetime(2026, 10, 4, 1, 0, tzinfo=KST), datetime(2026, 10, 3, 23, 0, tzinfo=KST)),
    ],
)
def test_latest_base_at_waits_ten_minutes_after_issue(now: datetime, expected: datetime) -> None:
    assert latest_base_at(now) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("강수없음", ForecastValue(0.0, 0.0, True, "강수없음")),
        ("1mm 미만", ForecastValue(0.0, 1.0, False, "1mm 미만")),
        ("1.0mm 미만", ForecastValue(0.0, 1.0, False, "1.0mm 미만")),
        ("6.2mm", ForecastValue(6.2, 6.2, True, "6.2mm")),
        ("30.0~50.0mm", ForecastValue(30.0, 50.0, False, "30.0~50.0mm")),
        ("50.0mm 이상", ForecastValue(50.0, None, False, "50.0mm 이상")),
    ],
)
def test_precipitation_categories(raw: str, expected: ForecastValue) -> None:
    hours = normalize(BASE_AT, [item("PCP", raw)]).hours

    assert hours[0].values[Element.PRECIPITATION_MM_PER_H] == expected


def test_snow_and_wind_values_and_unrelated_categories() -> None:
    items = [item("SNO", "적설없음"), item("WSD", "4.3"), item("TMP", "18")]
    values = normalize(BASE_AT, items).hours[0].values

    assert values == {
        Element.SNOWFALL_CM_PER_H: ForecastValue(0.0, 0.0, True, "적설없음"),
        Element.WIND_SPEED_MPS: ForecastValue(4.3, 4.3, True, "4.3"),
    }


@pytest.mark.parametrize("raw", ["900", "-999", "알수없음", ""])
def test_missing_or_unreadable_values_are_left_missing(raw: str) -> None:
    hours = normalize(BASE_AT, [item("WSD", raw), item("PCP", "강수없음")]).hours

    assert Element.WIND_SPEED_MPS not in hours[0].values


def test_normalize_groups_by_forecast_time_in_kst() -> None:
    weather = normalize(BASE_AT, [item("WSD", "1", "1000"), item("WSD", "2", "0900")])

    assert [h.valid_at for h in weather.hours] == [
        datetime(2026, 10, 5, 9, tzinfo=KST),
        datetime(2026, 10, 5, 10, tzinfo=KST),
    ]
    assert weather.forecast_issued_at == BASE_AT


def test_fetch_reads_all_pages_with_query_for_base_time_and_grid() -> None:
    calls: list[dict[str, str]] = []
    pages = [page([item("WSD", "1")], total=2), page([item("PCP", "강수없음")], total=2)]

    def fake_get(url: str, params: dict[str, str], timeout_s: float) -> bytes:
        calls.append(params)
        return pages[len(calls) - 1]

    fetched = fetch_vilage_forecast(AUTH, BASE_AT, 60, 127, fake_get)

    assert len(fetched.items) == 2
    assert [c["pageNo"] for c in calls] == ["1", "2"]
    assert calls[0]["base_date"] == "20261004"
    assert calls[0]["base_time"] == "1400"
    assert (calls[0]["nx"], calls[0]["ny"]) == ("60", "127")


def test_missing_key_fails_without_calling_api() -> None:
    def must_not_call(url: str, params: dict[str, str], timeout_s: float) -> bytes:
        raise AssertionError("호출하면 안 됨")

    with pytest.raises(ForecastFetchError, match="인증키가 설정되지 않음"):
        fetch_vilage_forecast(KmaAuth(DATA_GO_KR, ""), BASE_AT, 60, 127, must_not_call)


def test_error_result_code_is_reported_with_message() -> None:
    with pytest.raises(ForecastFetchError, match="기상청 오류 03"):
        fetch_vilage_forecast(AUTH, BASE_AT, 60, 127, lambda *_: page([], 0, code="03"))


def test_non_json_response_keeps_the_start_of_body_as_reason() -> None:
    xml = b"<OpenAPI_ServiceResponse><returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR"

    with pytest.raises(ForecastFetchError, match="SERVICE_KEY_IS_NOT_REGISTERED_ERROR"):
        fetch_vilage_forecast(AUTH, BASE_AT, 60, 127, lambda *_: xml)


def test_network_failure_becomes_fetch_error() -> None:
    def fail(url: str, params: dict[str, str], timeout_s: float) -> bytes:
        raise urllib.error.URLError("timed out")

    with pytest.raises(ForecastFetchError, match="연결 실패"):
        fetch_vilage_forecast(AUTH, BASE_AT, 60, 127, fail)


def test_api_hub_uses_its_own_url_and_auth_key_parameter() -> None:
    seen: list[tuple[str, dict[str, str]]] = []

    def fake_get(url: str, params: dict[str, str], timeout_s: float) -> bytes:
        seen.append((url, params))
        return page([item("WSD", "1")], total=1)

    fetch_vilage_forecast(KmaAuth(API_HUB, "hub-key"), BASE_AT, 60, 127, fake_get)

    url, params = seen[0]
    assert url.startswith("https://apihub.kma.go.kr/")
    assert params["authKey"] == "hub-key"
    assert "serviceKey" not in params


def test_http_error_keeps_kma_reason_from_body() -> None:
    # 2026-10-04 API허브가 실제로 돌려준 본문(유효한 키, 단기예보 활용신청 전).
    body = """{
  "result" : {
    "status" : 403,
    "message" : "활용신청이 필요한 API 입니다. 활용신청 후 다시 시도해 주십시오."
  }
}""".encode()

    def forbidden(url: str, params: dict[str, str], timeout_s: float) -> bytes:
        raise urllib.error.HTTPError(url, 403, "Forbidden", Message(), io.BytesIO(body))

    reason = "기상청 API허브 HTTP 403: .*활용신청이 필요한 API"
    with pytest.raises(ForecastFetchError, match=reason):
        fetch_vilage_forecast(KmaAuth(API_HUB, "hub-key"), BASE_AT, 60, 127, forbidden)
