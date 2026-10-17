"""공휴일 응답 해석. 응답 예시는 2026-10-17 실제 호출 결과(키는 응답에 없다)."""

import json
import urllib.error
from datetime import date
from email.message import Message
from io import BytesIO
from pathlib import Path

import pytest

from engine.holidays import HolidayFetchError, fetch_holidays, parse_holidays

DATA = Path(__file__).parent / "data" / "spcde_rest_2026.json"


def test_real_year_response_has_substitute_holidays() -> None:
    days = parse_holidays(DATA.read_bytes())

    assert len(days) == 22  # 2026년 실제 응답 totalCount
    assert days[date(2026, 2, 17)] == "설날"
    assert days[date(2026, 10, 3)] == "개천절"
    assert any(name.startswith("대체공휴일") for name in days.values())


def test_single_item_comes_as_object_not_list() -> None:
    # 2026-07 실제 응답: 항목이 하나면 item이 객체
    body = (
        '{"response":{"header":{"resultCode":"00","resultMsg":"NORMAL SERVICE."},"body":{"items":'
        '{"item":{"dateKind":"01","dateName":"제헌절","isHoliday":"Y","locdate":20260717,"seq":1}}'
        ',"numOfRows":10,"pageNo":1,"totalCount":1}}}'
    ).encode()
    assert parse_holidays(body) == {date(2026, 7, 17): "제헌절"}


def test_empty_items_and_non_holidays_are_skipped() -> None:
    empty = {"response": {"header": {"resultCode": "00"}, "body": {"items": "", "totalCount": 0}}}
    assert parse_holidays(json.dumps(empty).encode()) == {}
    item = {"dateName": "기념일", "isHoliday": "N", "locdate": 20260505}
    not_rest = {"response": {"header": {"resultCode": "00"}, "body": {"items": {"item": [item]}}}}
    assert parse_holidays(json.dumps(not_rest).encode()) == {}


def test_error_code_and_http_failure_raise_with_reason() -> None:
    error = {
        "response": {"header": {"resultCode": "30", "resultMsg": "SERVICE KEY IS NOT REGISTERED"}}
    }
    with pytest.raises(HolidayFetchError, match="오류 코드 30"):
        parse_holidays(json.dumps(error).encode())

    def forbidden(url: str, params: dict[str, str], timeout_s: float) -> bytes:
        raise urllib.error.HTTPError(url, 403, "Forbidden", Message(), BytesIO(b""))

    with pytest.raises(HolidayFetchError, match="HTTP 403"):
        fetch_holidays("key", 2026, forbidden)
    with pytest.raises(HolidayFetchError, match="인증키가 없음"):
        fetch_holidays("", 2026, forbidden)
