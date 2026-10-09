"""기상청 단기예보 조회서비스(getVilageFcst) 수집·정규화.

형식 출처: 공공데이터포털 "기상청_단기예보 ((구)_동네예보) 조회서비스" 오픈API 활용가이드.
같은 서비스를 기상청 API허브(apihub.kma.go.kr, typ02/openApi)도 제공한다.
주소와 키 이름(authKey)만 다르다.
- 발표 시각 02·05·08·11·14·17·20·23시, 각 발표 10분 이후 제공
- 응답 항목: baseDate, baseTime, category, fcstDate, fcstTime, fcstValue, nx, ny
- PCP(1시간 강수량)·SNO(1시간 신적설)는 범주 문자열, WSD(풍속 m/s)·TMP(1시간 기온 ℃)·REH(습도 %)는
  숫자 문자열
- ±900 이상 값은 결측
실제 응답과의 대조는 활용신청 후 한다(docs/plan.md S02-2). 2026-10-04 확인한 실제 오류 응답:
- 공공데이터포털, 등록 안 된 키: HTTP 403,
  {"OpenAPI_ServiceResponse": {... "errMsg": "SERVICE_KEY_IS_NOT_REGISTERED_ERROR"}}
- API허브, 유효한 키·미신청 API: HTTP 403,
  {"result": {"status": 403, "message": "활용신청이 필요한 API 입니다. ..."}}
- API허브, 유효하지 않은 키: HTTP 401,
  {"result": {"status": 401, "message": "유효한 인증키가 아닙니다."}}
"""

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from engine.forecast.sensible import sensible_temperature_c
from engine.judgment.types import Element, ForecastValue, HourlyForecast, WeatherInput
from engine.kst import KST

logger = logging.getLogger(__name__)

_ERROR_BODY_CHARS = 300
BASE_HOURS = (2, 5, 8, 11, 14, 17, 20, 23)
AVAILABLE_AFTER = timedelta(minutes=10)
PAGE_ROWS = 1000
TIMEOUT_S = 10.0
_MISSING_ABS = 900.0

# (URL, 쿼리, 제한 시간 초) → 응답 본문. 테스트에서는 가짜 함수로 바꾼다.
HttpGet = Callable[[str, dict[str, str], float], bytes]


@dataclass(frozen=True, slots=True)
class KmaEndpoint:
    name: str
    url: str
    key_param: str


DATA_GO_KR = KmaEndpoint(
    "공공데이터포털",
    "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst",
    "serviceKey",
)
API_HUB = KmaEndpoint(
    "기상청 API허브",
    "https://apihub.kma.go.kr/api/typ02/openApi/VilageFcstInfoService_2.0/getVilageFcst",
    "authKey",
)


@dataclass(frozen=True, slots=True)
class KmaAuth:
    endpoint: KmaEndpoint
    key: str


class ForecastFetchError(RuntimeError):
    """예보를 받지 못했다. 메시지에 원인을 담아 수집 기록에 남긴다."""


@dataclass(frozen=True, slots=True)
class FetchedForecast:
    base_at: datetime
    nx: int
    ny: int
    items: tuple[dict[str, Any], ...]  # 원자료 그대로(저장용)


def latest_base_at(now: datetime) -> datetime:
    """now 시점에 받을 수 있는 가장 최근 발표 시각."""
    if now.tzinfo is None:
        raise ValueError("now에 시간대가 없음")
    local = now.astimezone(KST)
    for days_back in (0, 1):
        day = (local - timedelta(days=days_back)).replace(minute=0, second=0, microsecond=0)
        for hour in reversed(BASE_HOURS):
            base = day.replace(hour=hour)
            if base + AVAILABLE_AFTER <= local:
                return base
    raise AssertionError("하루 전 23시 발표는 항상 제공된다")


def next_base_at(now: datetime) -> datetime:
    """now 이후 처음 받을 수 있게 될 발표 시각(제공은 AVAILABLE_AFTER 뒤)."""
    latest = latest_base_at(now)
    later = [h for h in BASE_HOURS if h > latest.hour]
    if later:
        return latest.replace(hour=later[0])
    return (latest + timedelta(days=1)).replace(hour=BASE_HOURS[0])


def urllib_get(url: str, params: dict[str, str], timeout_s: float) -> bytes:
    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(full_url, timeout=timeout_s) as response:
        body: bytes = response.read()
        return body


def fetch_vilage_forecast(
    auth: KmaAuth, base_at: datetime, nx: int, ny: int, http_get: HttpGet = urllib_get
) -> FetchedForecast:
    if not auth.key:
        raise ForecastFetchError(
            "기상청 인증키가 설정되지 않음 (KMA_APIHUB_KEY 또는 KMA_SERVICE_KEY)"
        )
    base_local = base_at.astimezone(KST)
    items: list[dict[str, Any]] = []
    page = 1
    while True:
        params = {
            auth.endpoint.key_param: auth.key,
            "pageNo": str(page),
            "numOfRows": str(PAGE_ROWS),
            "dataType": "JSON",
            "base_date": base_local.strftime("%Y%m%d"),
            "base_time": base_local.strftime("%H%M"),
            "nx": str(nx),
            "ny": str(ny),
        }
        body = _get(http_get, auth.endpoint, params)
        page_items, total_count = _parse_page(body)
        items.extend(page_items)
        if len(items) >= total_count or not page_items:
            break
        page += 1
    logger.info("예보 수집 base_at=%s nx=%s ny=%s items=%s", base_local, nx, ny, len(items))
    return FetchedForecast(base_at=base_local, nx=nx, ny=ny, items=tuple(items))


def _get(http_get: HttpGet, endpoint: KmaEndpoint, params: dict[str, str]) -> bytes:
    try:
        return http_get(endpoint.url, params, TIMEOUT_S)
    except urllib.error.HTTPError as error:
        # 인증·신청 문제의 사유는 본문에 있다(모듈 설명의 실제 오류 응답). 본문을 남긴다.
        raise ForecastFetchError(
            f"{endpoint.name} HTTP {error.code}: {_snippet(error.read())}"
        ) from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise ForecastFetchError(f"연결 실패: {error}") from error


def _parse_page(body: bytes) -> tuple[list[dict[str, Any]], int]:
    try:
        data = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        # 게이트웨이 오류 등은 XML로 올 수 있다. 원인을 알 수 있게 앞부분을 남긴다.
        raise ForecastFetchError(f"응답이 JSON이 아님: {_snippet(body)}") from error
    try:
        header = data["response"]["header"]
        if header["resultCode"] != "00":
            raise ForecastFetchError(f"기상청 오류 {header['resultCode']} {header['resultMsg']}")
        body_part = data["response"]["body"]
        raw_items = body_part["items"]["item"]
        total_count = int(body_part["totalCount"])
    except (KeyError, TypeError, ValueError) as error:
        raise ForecastFetchError(f"응답 형식이 예상과 다름: {error!r}") from error
    if not isinstance(raw_items, list):
        raise ForecastFetchError("응답 items.item이 목록이 아님")
    return raw_items, total_count


def _snippet(body: bytes) -> str:
    return " ".join(body.decode("utf-8", errors="replace").split())[:_ERROR_BODY_CHARS]


def rain_probability_by_hour(items: Iterable[dict[str, Any]]) -> dict[datetime, int]:
    """원자료의 강수확률(POP, %)을 예보 시각별로. 해석할 수 없는 값은 버린다(공온지수 v2, D-052)."""
    out: dict[datetime, int] = {}
    for item in items:
        if str(item.get("category")) != "POP":
            continue
        try:
            valid_at = _kst_datetime(str(item["fcstDate"]), str(item["fcstTime"]))
            pct = int(str(item.get("fcstValue", "")).strip())
        except (KeyError, ValueError):
            logger.warning("강수확률 해석 불가: %r", item)
            continue
        if 0 <= pct <= 100:
            out[valid_at] = pct
    return out


def normalize(base_at: datetime, items: Iterable[dict[str, Any]]) -> WeatherInput:
    """원자료 → 판정 입력. 해석할 수 없는 값은 버려서 판정에서 누락(판정 불가)으로 처리되게 한다."""
    by_time: dict[datetime, dict[Element, ForecastValue]] = {}
    for item in items:
        element = _CATEGORY_ELEMENT.get(str(item.get("category")))
        if element is None:
            continue
        try:
            valid_at = _kst_datetime(str(item["fcstDate"]), str(item["fcstTime"]))
        except (KeyError, ValueError):
            logger.warning("예보 시각 해석 불가: %r", item)
            continue
        raw = str(item.get("fcstValue", "")).strip()
        value = _PARSERS[element](raw)
        if value is None:
            logger.warning("예보값 해석 불가 category=%s value=%r", item.get("category"), raw)
            continue
        by_time.setdefault(valid_at, {})[element] = value
    for values in by_time.values():
        _add_sensible_temperature(values)
    hours = tuple(HourlyForecast(t, by_time[t]) for t in sorted(by_time))
    return WeatherInput(forecast_issued_at=base_at.astimezone(KST), hours=hours)


def _add_sensible_temperature(values: dict[Element, ForecastValue]) -> None:
    """같은 시각의 기온·습도로 체감온도를 만든다. 하나라도 없으면 만들지 않는다(판정 불가)."""
    temperature = values.get(Element.TEMPERATURE_C)
    humidity = values.get(Element.HUMIDITY_PCT)
    if temperature is None or humidity is None:
        return
    value = sensible_temperature_c(temperature.lower, humidity.lower)
    raw = f"{value:.1f}(기온 {temperature.raw}℃·습도 {humidity.raw}%)"
    values[Element.SENSIBLE_TEMPERATURE_C] = ForecastValue.exact(value, raw)


def _kst_datetime(yyyymmdd: str, hhmm: str) -> datetime:
    if len(yyyymmdd) != 8 or len(hhmm) != 4:
        raise ValueError(f"예보 시각 형식 오류: {yyyymmdd} {hhmm}")
    return datetime(
        int(yyyymmdd[:4]), int(yyyymmdd[4:6]), int(yyyymmdd[6:]),
        int(hhmm[:2]), int(hhmm[2:]), tzinfo=KST,
    )  # fmt: skip


_NUMBER = r"(\d+(?:\.\d+)?)"


def _amount_parser(unit: str, none_text: str) -> Callable[[str], ForecastValue | None]:
    below = re.compile(rf"^{_NUMBER}\s*{unit}\s*미만$")
    at_least = re.compile(rf"^{_NUMBER}\s*{unit}\s*이상$")
    between = re.compile(rf"^{_NUMBER}\s*~\s*{_NUMBER}\s*{unit}$")
    exact = re.compile(rf"^{_NUMBER}\s*(?:{unit})?$")

    def parse(raw: str) -> ForecastValue | None:
        # 활용가이드: "-", null, 0은 없음으로 표시한다.
        if raw in (none_text, "-", "0", "0.0"):
            return ForecastValue.exact(0.0, raw)
        if m := below.match(raw):
            return ForecastValue(0.0, float(m[1]), False, raw)
        if m := at_least.match(raw):
            return ForecastValue(float(m[1]), None, False, raw)
        if m := between.match(raw):
            return ForecastValue(float(m[1]), float(m[2]), False, raw)
        if m := exact.match(raw):
            return _number(float(m[1]), raw)
        return None

    return parse


def _parse_number(raw: str) -> ForecastValue | None:
    try:
        return _number(float(raw), raw)
    except ValueError:
        return None


def _parse_humidity(raw: str) -> ForecastValue | None:
    value = _parse_number(raw)
    return value if value is not None and 0 <= value.lower <= 100 else None


def _number(value: float, raw: str) -> ForecastValue | None:
    if abs(value) >= _MISSING_ABS:
        return None
    return ForecastValue.exact(value, raw)


_CATEGORY_ELEMENT = {
    "WSD": Element.WIND_SPEED_MPS,
    "PCP": Element.PRECIPITATION_MM_PER_H,
    "SNO": Element.SNOWFALL_CM_PER_H,
    "TMP": Element.TEMPERATURE_C,
    "REH": Element.HUMIDITY_PCT,
}
_PARSERS: dict[Element, Callable[[str], ForecastValue | None]] = {
    Element.WIND_SPEED_MPS: _parse_number,
    Element.PRECIPITATION_MM_PER_H: _amount_parser("mm", "강수없음"),
    Element.SNOWFALL_CM_PER_H: _amount_parser("cm", "적설없음"),
    Element.TEMPERATURE_C: _parse_number,
    Element.HUMIDITY_PCT: _parse_humidity,
}
