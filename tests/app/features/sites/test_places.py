"""현장 위치 찾기(/sites/places). 카카오 API는 가짜 http_get으로 바꾼다.

응답 본문은 Kakao Developers '키워드로 장소 검색' 문서의 응답 구조(meta, documents[]의
place_name·address_name·road_address_name·category_name·x·y)를 따르고 값은 테스트용이다.
"""

import json
import urllib.error
from email.message import Message
from io import BytesIO
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.features.sites.places import get_place_http_get
from app.main import create_app


def kakao_body(*documents: dict[str, Any]) -> bytes:
    meta = {"total_count": len(documents), "pageable_count": len(documents), "is_end": True}
    return json.dumps({"meta": meta, "documents": list(documents)}, ensure_ascii=False).encode()


SEOUL_CITY_HALL = {
    "place_name": "서울특별시청",
    "address_name": "서울 중구 태평로1가 31",
    "road_address_name": "서울 중구 세종대로 110",
    "category_name": "사회,공공기관 > 행정기관 > 시청",
    "x": "126.978652258309",
    "y": "37.566826004661",
}


class FakeKakao:
    def __init__(self, body: bytes = b"", error: Exception | None = None) -> None:
        self.body = body
        self.error = error
        self.calls: list[tuple[dict[str, str], dict[str, str]]] = []

    def __call__(
        self, url: str, params: dict[str, str], headers: dict[str, str], timeout_s: float
    ) -> bytes:
        self.calls.append((params, headers))
        if self.error is not None:
            raise self.error
        return self.body


def client_with(fake: FakeKakao, key: str = "kakao-key") -> TestClient:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings("", "", kakao_rest_api_key=key)
    app.dependency_overrides[get_place_http_get] = lambda: fake
    return TestClient(app)


def test_search_returns_address_and_coordinates_for_the_form() -> None:
    fake = FakeKakao(kakao_body(SEOUL_CITY_HALL))

    data = client_with(fake).get("/sites/places", params={"q": "서울시청"}).json()

    assert data["places"] == [
        {
            "name": "서울특별시청",
            "address": "서울 중구 세종대로 110",  # 도로명주소 우선
            "category": "사회,공공기관 > 행정기관 > 시청",
            "latitude_deg": 37.566826004661,  # y가 위도
            "longitude_deg": 126.978652258309,  # x가 경도
        }
    ]
    params, headers = fake.calls[0]
    assert params["query"] == "서울시청"
    assert headers == {"Authorization": "KakaoAK kakao-key"}


def test_lot_number_address_is_used_when_no_road_address() -> None:
    doc = {**SEOUL_CITY_HALL, "road_address_name": ""}
    data = client_with(FakeKakao(kakao_body(doc))).get("/sites/places", params={"q": "시청"}).json()

    assert data["places"][0]["address"] == "서울 중구 태평로1가 31"


def test_result_without_coordinates_is_not_offered() -> None:
    broken = {**SEOUL_CITY_HALL, "x": ""}
    data = client_with(FakeKakao(kakao_body(broken))).get("/sites/places", params={"q": "시청"})

    assert data.json()["places"] == []


@pytest.mark.parametrize("query", ["", "서", "  서  "])
def test_too_short_query_does_not_call_kakao(query: str) -> None:
    fake = FakeKakao(kakao_body(SEOUL_CITY_HALL))

    data = client_with(fake).get("/sites/places", params={"q": query}).json()

    assert data == {"places": [], "message": None}
    assert fake.calls == []


def test_missing_key_explains_manual_entry_without_calling_kakao() -> None:
    fake = FakeKakao(kakao_body(SEOUL_CITY_HALL))

    data = client_with(fake, key="").get("/sites/places", params={"q": "서울시청"}).json()

    assert data["places"] == []
    assert "KAKAO_REST_API_KEY" in data["message"]
    assert fake.calls == []


def test_kakao_error_reason_is_shown_not_500() -> None:
    body = b'{"errorType":"AccessDeniedError","message":"cannot find appkey"}'
    error = urllib.error.HTTPError("u", 401, "Unauthorized", Message(), BytesIO(body))

    response = client_with(FakeKakao(error=error)).get("/sites/places", params={"q": "서울시청"})

    assert response.status_code == 200
    assert "카카오 HTTP 401" in response.json()["message"]
    assert "cannot find appkey" in response.json()["message"]


def test_no_results_suggests_other_name_or_manual_entry() -> None:
    data = (
        client_with(FakeKakao(kakao_body())).get("/sites/places", params={"q": "없는현장"}).json()
    )

    assert data["places"] == []
    assert "직접 입력" in data["message"]
