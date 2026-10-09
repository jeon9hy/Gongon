"""현장 주소 → 위경도: 카카오 로컬 API '주소 검색하기'(D-047, D-022 대체).

카카오맵에 장소로 등록되지 않은 공사 현장도 지번·도로명 주소만으로 좌표를 얻는다.
형식 출처: Kakao Developers 문서 > 로컬 > 주소 검색하기
GET https://dapi.kakao.com/v2/local/search/address.json
(헤더 `Authorization: KakaoAK {REST API 키}`).
응답 documents[]의 address_name·address(지번)·road_address(도로명, 없으면 null)와
x(경도)·y(위도) 문자열을 쓴다. 2026-10-08 실제 응답으로 대조했다(도로명·지번 각 1건).
키는 서버에만 두고 브라우저에는 결과만 보낸다. 카카오맵 사용 설정이 꺼져 있으면
HTTP 403 {"errorType":"NotAuthorizedError",
 "message":"App(앱 이름) disabled OPEN_MAP_AND_LOCAL service."}
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

logger = logging.getLogger(__name__)

ADDRESS_SEARCH_URL = "https://dapi.kakao.com/v2/local/search/address.json"
RESULT_SIZE = 5  # 문서상 1~30
TIMEOUT_S = 5.0
QUERY_MIN = 2
QUERY_MAX = 100
_ERROR_BODY_CHARS = 200

# (URL, 쿼리, 헤더, 제한 시간 초) → 응답 본문. 테스트에서는 가짜 함수로 바꾼다.
HttpGetWithHeaders = Callable[[str, dict[str, str], dict[str, str], float], bytes]


class PlaceSearchError(RuntimeError):
    """주소를 검색하지 못했다. 메시지에 원인을 담는다."""


@dataclass(frozen=True, slots=True)
class Place:
    name: str  # 건물 이름. 없으면 빈 문자열(빈 땅 지번 등)
    road_address: str  # 도로명 주소. 없으면 빈 문자열(빈 땅 지번 등)
    lot_address: str  # 지번 주소
    latitude_deg: float
    longitude_deg: float

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def urllib_get_with_headers(
    url: str, params: dict[str, str], headers: dict[str, str], timeout_s: float
) -> bytes:
    request = urllib.request.Request(f"{url}?{urllib.parse.urlencode(params)}", headers=headers)
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        body: bytes = response.read()
        return body


def get_place_http_get() -> HttpGetWithHeaders:
    """FastAPI 의존성. 테스트에서 가짜 응답 함수로 바꾼다."""
    return urllib_get_with_headers


def search_places(query: str, api_key: str, http_get: HttpGetWithHeaders) -> tuple[Place, ...]:
    if not api_key:
        raise PlaceSearchError("주소 검색 키(KAKAO_REST_API_KEY)가 설정되지 않음")
    params = {"query": query, "size": str(RESULT_SIZE)}
    headers = {"Authorization": f"KakaoAK {api_key}"}
    try:
        body = http_get(ADDRESS_SEARCH_URL, params, headers, TIMEOUT_S)
    except urllib.error.HTTPError as error:
        raise PlaceSearchError(f"카카오 HTTP {error.code}: {_snippet(error.read())}") from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise PlaceSearchError(f"연결 실패: {error}") from error
    try:
        documents = json.loads(body)["documents"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise PlaceSearchError(f"응답 형식이 예상과 다름: {_snippet(body)}") from error
    places = []
    for doc in documents:
        place = _place(doc)
        if place is None:
            logger.warning("좌표를 읽을 수 없는 주소 결과를 건너뜀: %r", doc)
            continue
        places.append(place)
    return tuple(places)


def _place(doc: Any) -> Place | None:
    if not isinstance(doc, dict):
        return None
    try:
        longitude = float(doc["x"])
        latitude = float(doc["y"])
    except (KeyError, TypeError, ValueError):
        return None  # 좌표가 없는 결과는 채울 값이 없으므로 보여주지 않는다
    road = _section(doc, "road_address")  # 도로명주소가 없으면 null
    lot = _section(doc, "address")
    return Place(
        name=str(road.get("building_name") or ""),
        road_address=str(road.get("address_name") or ""),
        lot_address=str(lot.get("address_name") or ""),
        latitude_deg=latitude,
        longitude_deg=longitude,
    )


def _section(doc: dict[str, Any], key: str) -> dict[str, Any]:
    value = doc.get(key)
    return value if isinstance(value, dict) else {}


def _snippet(body: bytes) -> str:
    return " ".join(body.decode("utf-8", errors="replace").split())[:_ERROR_BODY_CHARS]
