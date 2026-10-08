"""기상청 중기예보 조회서비스(getMidLandFcst) 수집·해석(D-042).

주간 보기에서 단기예보 범위 밖 날짜에 참고로 쓴다.

형식 출처: 공공데이터포털 "기상청_중기예보 조회서비스" 오픈API 활용가이드(241128, ZIP 251212).
- 발표 06·18시(일 2회), 최근 24시간 자료만 제공
- 6시 발표는 발표일로부터 4~10일, 18시 발표는 5~10일(2024.11.28. 14시~)
- rnSt{n}Am/Pm: n일 후 오전/오후 강수 확률(%), 8~10일은 rnSt{n}(하루)
- wf{n}Am/Pm: n일 후 오전/오후 날씨예보.
  하늘상태(맑음·구름많음·흐림)와 현상(비·눈·비/눈·소나기)의 조합
풍속·강수량·적설량은 없다. 그래서 기준값과 직접 비교하지 않는다.
2026-10-08 실제 응답: tests/engine/forecast/data/kma_mid_getMidLandFcst_202610080600_11B00000.json
"""

import json
import urllib.error
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from engine.forecast.kma import ForecastFetchError, HttpGet
from engine.kst import KST

MID_LAND_URL = "https://apis.data.go.kr/1360000/MidFcstInfoService/getMidLandFcst"
ISSUE_HOURS = (6, 18)
TIMEOUT_S = 10.0
_ERROR_BODY_CHARS = 300

# 활용가이드 "중기육상예보구역 코드 정보 표"(10개 구역).
LAND_REGIONS: dict[str, str] = {
    "11B00000": "서울, 인천, 경기도",
    "11D10000": "강원도영서",
    "11D20000": "강원도영동",
    "11C20000": "대전, 세종, 충청남도",
    "11C10000": "충청북도",
    "11F20000": "광주, 전라남도",
    "11F10000": "전북자치도",
    "11H10000": "대구, 경상북도",
    "11H20000": "부산, 울산, 경상남도",
    "11G00000": "제주도",
}
# 주소 첫 낱말(시·도) → 구역. 카카오 주소의 줄인 이름과 정식 이름을 모두 받는다.
_SIDO_REGION: dict[str, str] = {
    **dict.fromkeys(("서울", "서울시", "서울특별시", "인천", "인천광역시", "경기", "경기도"),
                    "11B00000"),
    **dict.fromkeys(("대전", "대전광역시", "세종", "세종시", "세종특별자치시", "충남",
                     "충청남도"), "11C20000"),
    **dict.fromkeys(("충북", "충청북도"), "11C10000"),
    **dict.fromkeys(("광주", "광주광역시", "전남", "전라남도"), "11F20000"),
    **dict.fromkeys(("전북", "전라북도", "전북특별자치도"), "11F10000"),
    **dict.fromkeys(("대구", "대구광역시", "경북", "경상북도"), "11H10000"),
    **dict.fromkeys(("부산", "부산광역시", "울산", "울산광역시", "경남", "경상남도"),
                    "11H20000"),
    **dict.fromkeys(("제주", "제주도", "제주특별자치도"), "11G00000"),
}  # fmt: skip
_GANGWON = ("강원", "강원도", "강원특별자치도")
# 강원은 시·군으로 영서·영동을 가른다. 출처: 활용가이드 ZIP의 중기기온예보구역코드(2025.12)에서
# 11D2(강원영동) 아래 도시. 대관령은 평창군 안의 지점이라 시·군 이름으로 쓰지 않는다(평창은 11D1).
_GANGWON_EAST = ("태백", "속초", "고성", "양양", "강릉", "동해", "삼척")


def land_region_for(address: str) -> str | None:
    """주소 → 중기육상예보구역 코드. 시·도를 알 수 없으면 None(중기예보를 쓰지 않음)."""
    words = address.split()
    if not words:
        return None
    if words[0] in _GANGWON:
        if len(words) < 2:
            return None  # 영서·영동을 단정하지 않는다
        county = words[1].removesuffix("시").removesuffix("군")
        return "11D20000" if county in _GANGWON_EAST else "11D10000"
    return _SIDO_REGION.get(words[0])


@dataclass(frozen=True, slots=True)
class MidHalfDay:
    """하루의 오전 또는 오후(8일 후부터는 하루 전체)."""

    part: str  # "오전" | "오후" | "하루"
    rain_probability_pct: int | None
    weather: str | None  # 활용가이드 날씨예보 문구 그대로


@dataclass(frozen=True, slots=True)
class MidLandForecast:
    issued_at: datetime  # tmFc
    region_id: str
    days: dict[date, tuple[MidHalfDay, ...]]


def latest_issue_at(now: datetime) -> datetime:
    """now 이전의 가장 최근 발표 시각(06·18시). 실제 제공 지연은 호출 결과로 판단한다."""
    if now.tzinfo is None:
        raise ValueError("now에 시간대가 없음")
    local = now.astimezone(KST)
    for days_back in (0, 1):
        day = (local - timedelta(days=days_back)).replace(minute=0, second=0, microsecond=0)
        for hour in reversed(ISSUE_HOURS):
            issued = day.replace(hour=hour)
            if issued <= local:
                return issued
    raise AssertionError("하루 전 18시 발표는 항상 now 이전이다")


def previous_issue_at(issued_at: datetime) -> datetime:
    return issued_at - timedelta(hours=12)


def fetch_mid_land(
    service_key: str, issued_at: datetime, region_id: str, http_get: HttpGet
) -> dict[str, Any]:
    """원자료 item 하나(저장용). 자료가 아직 없으면 ForecastFetchError."""
    if not service_key:
        raise ForecastFetchError("공공데이터포털 인증키가 설정되지 않음 (KMA_SERVICE_KEY)")
    params = {
        "serviceKey": service_key,
        "pageNo": "1",
        "numOfRows": "10",
        "dataType": "JSON",
        "regId": region_id,
        "tmFc": issued_at.astimezone(KST).strftime("%Y%m%d%H%M"),
    }
    try:
        body = http_get(MID_LAND_URL, params, TIMEOUT_S)
    except urllib.error.HTTPError as error:
        raise ForecastFetchError(f"중기예보 HTTP {error.code}: {_snippet(error.read())}") from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise ForecastFetchError(f"중기예보 연결 실패: {error}") from error
    try:
        data = json.loads(body)
        header = data["response"]["header"]
        if header["resultCode"] != "00":
            raise ForecastFetchError(f"중기예보 오류 {header['resultCode']} {header['resultMsg']}")
        items = data["response"]["body"]["items"]["item"]
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ForecastFetchError(f"중기예보 응답이 JSON이 아님: {_snippet(body)}") from error
    except (KeyError, TypeError) as error:
        raise ForecastFetchError(f"중기예보 응답 형식이 예상과 다름: {error!r}") from error
    if not isinstance(items, list) or not items or not isinstance(items[0], dict):
        raise ForecastFetchError("중기예보 자료 없음")
    item: dict[str, Any] = items[0]
    return item


def parse_mid_land(issued_at: datetime, item: dict[str, Any]) -> MidLandForecast:
    """원자료 → 날짜별 오전·오후. 없는 항목은 None으로 둔다(정상값으로 채우지 않음)."""
    base_day = issued_at.astimezone(KST).date()
    days: dict[date, tuple[MidHalfDay, ...]] = {}
    for n in range(4, 11):
        if n <= 7:
            parts = tuple(
                MidHalfDay(
                    label, _pct(item.get(f"rnSt{n}{suffix}")), _text(item.get(f"wf{n}{suffix}"))
                )
                for suffix, label in (("Am", "오전"), ("Pm", "오후"))
            )
        else:
            parts = (MidHalfDay("하루", _pct(item.get(f"rnSt{n}")), _text(item.get(f"wf{n}"))),)
        if any(p.rain_probability_pct is not None or p.weather for p in parts):
            days[base_day + timedelta(days=n)] = parts
    return MidLandForecast(issued_at.astimezone(KST), str(item.get("regId", "")), days)


def _pct(raw: object) -> int | None:
    try:
        value = int(str(raw))
    except ValueError:
        return None
    return value if 0 <= value <= 100 else None


def _text(raw: object) -> str | None:
    text = "" if raw is None else str(raw).strip()
    return text or None


def _snippet(body: bytes) -> str:
    return " ".join(body.decode("utf-8", errors="replace").split())[:_ERROR_BODY_CHARS]
