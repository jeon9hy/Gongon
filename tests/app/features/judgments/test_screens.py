import pytest
from fastapi.testclient import TestClient

from app.main import create_app

client = TestClient(create_app())


def test_dashboard_shows_verdicts_and_disclaimer() -> None:
    html = client.get("/").text

    assert "내일 공사 ON?" in html
    assert "중지 검토" in html
    assert "최종 결정은 현장 책임자가 합니다" in html
    assert "예시 데이터" in html  # 가짜 데이터를 실제 판정처럼 보이지 않게 한다


def test_dashboard_does_not_show_undefined_index_or_sent_wording() -> None:
    html = client.get("/").text

    assert "공온지수" not in html  # 정의 전 표시 금지(D-010)
    assert "발송됨" not in html  # 실제 발송으로 읽히는 문구 금지(D-015)


def test_dashboard_selected_hour_and_element_change_the_value() -> None:
    html = client.get("/", params={"element": "wind", "hour": 14}).text

    assert "6.4 m/s" in html
    assert "14:00 풍속 예보" in html


@pytest.mark.parametrize("params", [{"hour": 6}, {"hour": 17}, {"element": "heat"}])
def test_dashboard_rejects_values_outside_sample_range(params: dict[str, str | int]) -> None:
    assert client.get("/", params=params).status_code == 422


def test_history_filter_keeps_only_matching_verdict() -> None:
    html = client.get("/judgments", params={"verdict": "판정 불가"}).text

    assert "예보 수집 실패" in html
    assert "09/30(수)" not in html  # 중지 검토 행


def test_history_site_filter_limits_rows_and_counts() -> None:
    html = client.get("/judgments", params={"site": "△△현장"}).text

    assert "09/30(수)" in html
    assert "10/02(금)" not in html  # ○○현장 행


def test_history_unknown_verdict_is_rejected() -> None:
    assert client.get("/judgments", params={"verdict": "안전"}).status_code == 422


def test_unavailable_judgment_has_no_forecast_issued_time_or_detail_link() -> None:
    html = client.get("/judgments", params={"verdict": "판정 불가"}).text

    assert "—" in html
    assert "/judgments/" not in html.split("<tbody>")[1]


def test_detail_shows_basis_and_pending_source_check() -> None:
    html = client.get("/judgments/1").text

    assert "원문 대조 필요" in html
    assert "예보 발표 2026-10-04 14:00 KST" in html
    assert "기상청 격자 (60, 127)" in html


def test_detail_unknown_id_returns_404() -> None:
    assert client.get("/judgments/999").status_code == 404


def test_sites_page_shows_grid_from_engine_and_unwired_save() -> None:
    html = client.get("/sites").text

    assert "(60, 127)" in html
    assert "저장은 아직 연결되지 않았습니다" in html


def test_sites_unknown_site_returns_404() -> None:
    assert client.get("/sites", params={"site_id": 99}).status_code == 404


def test_stylesheet_is_served() -> None:
    response = client.get("/static/gongon.css")

    assert response.status_code == 200
    assert "--accent: #C6F24E" in response.text
