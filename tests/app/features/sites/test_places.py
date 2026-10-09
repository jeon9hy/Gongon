"""현장 주소 → 위경도(/sites/places, 카카오 '주소 검색하기', D-047).

카카오 API는 가짜 http_get으로 바꾼다.

기본 문서는 2026-10-08 실제 응답(data/kakao_address_*.json)의 documents[0]이다.
빈 땅 지번 사례는 그 응답에서 road_address를 null로 바꾼 것이다(문서상 도로명이 없으면 null).
"""

import json
import urllib.error
from email.message import Message
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.features.sites.places import get_place_http_get
from app.main import create_app


def kakao_body(*documents: dict[str, Any]) -> bytes:
    meta = {"total_count": len(documents), "pageable_count": len(documents), "is_end": True}
    return json.dumps({"meta": meta, "documents": list(documents)}, ensure_ascii=False).encode()


DATA = Path(__file__).parent / "data"
LOT_RESPONSE = DATA / "kakao_address_lot_seoul_city_hall_2026-10-08.json"
ROAD_RESPONSE = DATA / "kakao_address_road_seoul_city_hall_2026-10-08.json"
LOT_DOCUMENTS = json.loads(LOT_RESPONSE.read_text(encoding="utf-8"))["documents"]
SEOUL_CITY_HALL: dict[str, Any] = LOT_DOCUMENTS[0]


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


def test_lot_number_returns_road_address_and_coordinates_for_the_form() -> None:
    fake = FakeKakao(LOT_RESPONSE.read_bytes())

    data = client_with(fake).get("/sites/places", params={"q": "서울 중구 태평로1가 31"}).json()

    assert data["places"] == [
        {
            "name": "서울특별시청",
            "road_address": "서울 중구 세종대로 110",
            "lot_address": "서울 중구 태평로1가 31",
            "latitude_deg": 37.566585446882,  # y가 위도
            "longitude_deg": 126.978203640984,  # x가 경도
        }
    ]
    assert data["message"] is None
    params, headers = fake.calls[0]
    assert params["query"] == "서울 중구 태평로1가 31"
    assert headers == {"Authorization": "KakaoAK kakao-key"}


def test_road_address_response_is_read() -> None:
    data = (
        client_with(FakeKakao(ROAD_RESPONSE.read_bytes()))
        .get("/sites/places", params={"q": "서울 중구 세종대로 110"})
        .json()
    )

    first = data["places"][0]
    assert first["road_address"] == "서울 중구 세종대로 110"
    assert 37.56 < first["latitude_deg"] < 37.57
    assert 126.97 < first["longitude_deg"] < 126.98


def test_vacant_lot_without_road_address_keeps_lot_number_only() -> None:
    # 건물이 없는 공사 부지는 도로명주소가 없다(road_address null).
    doc = {**SEOUL_CITY_HALL, "road_address": None}
    client = client_with(FakeKakao(kakao_body(doc)))
    data = client.get("/sites/places", params={"q": "태평로1가 31"})

    place = data.json()["places"][0]
    assert place["road_address"] == ""
    assert place["lot_address"] == "서울 중구 태평로1가 31"
    assert place["name"] == ""


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


def test_no_results_suggests_lot_number_or_manual_entry() -> None:
    client = client_with(FakeKakao(kakao_body()))
    data = client.get("/sites/places", params={"q": "없는 지번 999"}).json()

    assert data["places"] == []
    assert "직접 입력" in data["message"]


def test_autocomplete_script_is_in_page_body_not_title() -> None:
    # 스크립트가 <title> 안에 들어가면 실행되지 않는다(2026-10-04 실제로 발생).
    import app.features.sites.router  # noqa: F401  (sites 템플릿 폴더 등록)
    from app.core.templating import templates
    from app.features.sites.schemas import SiteForm, SitesView

    view = SitesView(items=(), site_id=None, form=SiteForm(), grid_text=None,
                     work_type_options=(), errors=(), saved=False)  # fmt: skip
    html = templates.get_template("sites/index.html").render(nav_active="sites", view=view)

    title = html[html.index("<title>") : html.index("</title>")]
    assert "<script" not in title
    assert html.index('id="site-road"') < html.index("<script>") < html.index("</main>")
    # 주소 찾기는 다음 우편번호 서비스 창이고, 이름으로 찾는 장소 목록은 쓰지 않는다(D-047).
    assert 'id="address-find"' in html and "postcode.v2.js" in html
    assert 'name="road_address"' in html and 'name="lot_address"' in html
