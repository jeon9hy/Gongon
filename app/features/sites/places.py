"""현장 위치 찾기: 카카오 로컬 API '키워드로 장소 검색'(D-022).

형식 출처: Kakao Developers 문서 > 로컬 > 키워드로 장소 검색
GET https://dapi.kakao.com/v2/local/search/keyword.json
(헤더 `Authorization: KakaoAK {REST API 키}`).
응답 documents[]의 place_name·address_name·road_address_name, x(경도)·y(위도) 문자열을 쓴다.
키는 서버에만 두고 브라우저에는 결과만 보낸다. 실제 응답 대조는 키 발급 후 한다.
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

KEYWORD_SEARCH_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
RESULT_SIZE = 8  # 문서상 1~15
TIMEOUT_S = 5.0
QUERY_MIN = 2
QUERY_MAX = 100
_ERROR_BODY_CHARS = 200

# (URL, 쿼리, 헤더, 제한 시간 초) → 응답 본문. 테스트에서는 가짜 함수로 바꾼다.
HttpGetWithHeaders = Callable[[str, dict[str, str], dict[str, str], float], bytes]


class PlaceSearchError(RuntimeError):
    """장소를 검색하지 못했다. 메시지에 원인을 담는다."""


@dataclass(frozen=True, slots=True)
class Place:
    name: str
    address: str  # 도로명주소가 있으면 도로명, 없으면 지번
    category: str
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
        raise PlaceSearchError("장소 검색 키(KAKAO_REST_API_KEY)가 설정되지 않음")
    params = {"query": query, "size": str(RESULT_SIZE)}
    headers = {"Authorization": f"KakaoAK {api_key}"}
    try:
        body = http_get(KEYWORD_SEARCH_URL, params, headers, TIMEOUT_S)
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
            logger.warning("좌표를 읽을 수 없는 장소 결과를 건너뜀: %r", doc)
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
    return Place(
        name=str(doc.get("place_name", "")),
        address=str(doc.get("road_address_name") or doc.get("address_name") or ""),
        category=str(doc.get("category_name", "")),
        latitude_deg=latitude,
        longitude_deg=longitude,
    )


def _snippet(body: bytes) -> str:
    return " ".join(body.decode("utf-8", errors="replace").split())[:_ERROR_BODY_CHARS]
