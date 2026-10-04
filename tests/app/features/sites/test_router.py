from typing import Any

import pytest
from fastapi.testclient import TestClient

VALID: dict[str, Any] = {
    "name": "○○현장",
    "address": "서울특별시",
    "latitude": "37.5665",
    "longitude": "126.9780",
    "work_start": "07:00",
    "work_end": "17:00",
    "work_start_date": "2026-10-01",
    "work_end_date": "2026-12-31",
    "work_types": ["철골 작업", "고소작업대"],
}


def create(client: TestClient, **changes: Any) -> Any:
    return client.post("/sites", data={**VALID, **changes}, follow_redirects=False)


def test_new_site_is_saved_with_kma_grid_and_listed(client: TestClient) -> None:
    response = create(client)

    assert response.status_code == 303
    page = client.get(response.headers["location"]).text
    assert "저장했습니다" in page
    assert "(60, 127)" in page  # 서울시청 위경도의 기상청 격자
    assert "철골 작업 외 1개" in page


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"latitude": "10.0", "longitude": "100.0"}, "기상청 단기예보 범위 밖"),
        ({"latitude": "abc"}, "위도·경도를 숫자로"),
        ({"work_start": "17:00", "work_end": "17:00"}, "종료는 시작보다 늦어야"),
        ({"work_start": "25:00"}, "00:00 형식"),
        ({"work_types": []}, "공종을 하나 이상"),
        ({"work_types": ["토공"]}, "알 수 없는 공종"),
        ({"address": "  "}, "주소를 1~200자로 입력하세요"),
        ({"work_start_date": ""}, "작업 기간(시작일·종료일)을 입력하세요"),
        (
            {"work_start_date": "2026-12-31", "work_end_date": "2026-10-01"},
            "종료일은 시작일과 같거나",
        ),
    ],
)
def test_invalid_site_is_not_saved_and_input_is_kept(
    client: TestClient, changes: dict[str, Any], message: str
) -> None:
    response = create(client, **changes)

    assert response.status_code == 422
    assert message in response.text
    assert 'value="○○현장"' in response.text  # 입력값을 다시 보여준다
    assert "○○현장</strong>" not in client.get("/sites").text  # 목록에 저장되지 않음


def test_site_update_changes_work_hours(client: TestClient) -> None:
    location = create(client).headers["location"]
    site_id = location.split("site_id=")[1].split("&")[0]

    response = client.post(
        f"/sites/{site_id}", data={**VALID, "work_end": "18:00"}, follow_redirects=False
    )

    assert response.status_code == 303
    assert "07:00–18:00" in client.get(f"/sites?site_id={site_id}").text


def test_unknown_site_returns_404(client: TestClient) -> None:
    assert client.get("/sites", params={"site_id": 99}).status_code == 404
    assert client.post("/sites/99", data=VALID).status_code == 404


def test_blank_site_name_uses_address_as_name(client: TestClient) -> None:
    location = create(client, name="", address="서울 중구 세종대로 110").headers["location"]

    assert "<strong>서울 중구 세종대로 110</strong>" in client.get(location).text


def test_new_site_form_starts_with_a_30_day_period_from_today(client: TestClient) -> None:
    page = client.get("/sites").text  # 고정 시각 2026-10-04

    assert 'name="work_start_date" value="2026-10-04"' in page
    assert 'name="work_end_date" value="2026-11-03"' in page
