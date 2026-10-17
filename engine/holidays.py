"""공휴일(한국천문연구원 특일 정보, 공공데이터포털 getRestDeInfo) 받기·해석.

- 한 해 공휴일을 한 번에 받는다(numOfRows=100). 대체공휴일·임시공휴일도 이 응답에 들어온다.
- 항목이 하나면 item이 목록이 아니라 객체로, 없으면 items가 빈 문자열로 온다(2026-10-17 실제 응답).
- isHoliday가 Y인 날만 공휴일로 본다. 해석할 수 없는 항목은 버리고 로그에 남긴다.
  공휴일은 달력 표시용이며 판정에 쓰지 않는다.
"""

import json
import logging
import urllib.error
from datetime import date
from typing import Any

from engine.forecast.kma import HttpGet

logger = logging.getLogger(__name__)

URL = "https://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo"
TIMEOUT_S = 10.0


class HolidayFetchError(RuntimeError):
    """공휴일을 받지 못했다. 달력은 공휴일 없이 보이고 원인은 로그에 남긴다."""


def fetch_holidays(service_key: str, year: int, http_get: HttpGet) -> dict[date, str]:
    if not service_key:
        raise HolidayFetchError("공공데이터포털 인증키가 없음(KMA_SERVICE_KEY)")
    params = {"serviceKey": service_key, "solYear": str(year), "_type": "json", "numOfRows": "100"}
    try:
        body = http_get(URL, params, TIMEOUT_S)
    except urllib.error.HTTPError as error:
        raise HolidayFetchError(f"특일 정보 HTTP {error.code}") from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise HolidayFetchError(f"특일 정보 연결 실패: {error}") from error
    return parse_holidays(body)


def parse_holidays(body: bytes) -> dict[date, str]:
    try:
        response = json.loads(body)["response"]
    except (ValueError, KeyError, TypeError) as error:
        raise HolidayFetchError(f"특일 정보 응답 형식 오류: {body[:120]!r}") from error
    code = str(response.get("header", {}).get("resultCode", ""))
    if code != "00":
        raise HolidayFetchError(f"특일 정보 오류 코드 {code}")
    items: Any = (response.get("body") or {}).get("items") or {}
    raw = items.get("item", []) if isinstance(items, dict) else []
    out: dict[date, str] = {}
    for item in raw if isinstance(raw, list) else [raw]:
        try:
            if item.get("isHoliday") != "Y":
                continue
            day = str(item["locdate"])
            on = date(int(day[:4]), int(day[4:6]), int(day[6:8]))
        except (AttributeError, KeyError, ValueError):
            logger.warning("특일 정보 항목 해석 불가: %r", item)
            continue
        name = str(item.get("dateName", "")).strip() or "공휴일"
        # 같은 날 이름이 둘이면(예: 선거일과 겹침) 함께 보인다.
        out[on] = f"{out[on]}·{name}" if on in out and name not in out[on] else name
    return out
